from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from foundry_databricks_genie.config import ConfigurationError
from foundry_databricks_genie.smoke import MAX_ROUNDS, SERVER_LABEL, _consent, _payloads, read_question, run_smoke


def answer() -> dict[str, object]:
    return {
        "type": "message", "role": "assistant",
        "content": [{"type": "output_text", "text": "synthetic-private-answer"}],
    }


def call(
    name: str = "query_space", output: str = '{"rows":[["synthetic-private-result"]]}',
    **changes: object,
) -> dict[str, object]:
    return {
        "type": "mcp_call", "id": "call_1", "server_label": SERVER_LABEL,
        "name": name, "status": "completed", "error": None, "output": output, **changes,
    }


def response(*output: object, status: str = "completed", **changes: object) -> Mock:
    return Mock(model_dump=Mock(return_value={
        "id": "resp_1", "status": status, "error": None, "output": list(output), **changes,
    }))


class SmokeTests(unittest.TestCase):
    def test_saved_agent_server_label_used_for_calls_and_approvals(self) -> None:
        approval = {"type": "mcp_approval_request", "id": "approval_1", "server_label": "portal_label"}
        client = Mock()
        client.responses.create.side_effect = [
            response(approval), response(call(server_label="portal_label"), answer()),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_smoke(
                client, "genie-agent", "test", approve_tools=True, server_label="portal_label"
            )
        self.assertEqual(result, 0)
        client.responses.create.side_effect = [response(call(server_label="unrelated"), answer())]
        with self.assertRaises(ConfigurationError):
            run_smoke(client, "genie-agent", "test", server_label="portal_label")

    def test_foundry_concatenated_structured_response_blocks(self) -> None:
        payload = '{"status":"COMPLETED","content":{}}'
        output = payload + "\n" + json.dumps({"structuredResponse": json.loads(payload)})
        self.assertIn({"status": "COMPLETED", "content": {}}, _payloads(output))
        result, _, _ = self.run_responses([response(call(output=output), answer())])
        self.assertEqual(result, 0)
        output = payload + '\n{"structuredResponse":{"status":"FAILED"}}'
        result, _, _ = self.run_responses([response(call(output=output), answer())])
        self.assertEqual(result, 4)

    def test_curated_pending_status_never_passes_as_completed_query(self) -> None:
        for status in ("PENDING_WAREHOUSE", "ASKING_AI", "EXECUTING_QUERY"):
            result, output, _ = self.run_responses([
                response(call(output=json.dumps({"status": status})), answer())
            ])
            self.assertEqual(result, 4)
            self.assertIn("not reached completed", output)

    def test_malformed_trailing_json_block_is_not_silently_discarded(self) -> None:
        with self.assertRaises(ConfigurationError):
            _payloads('{"status":"COMPLETED"}\n{"error":')

    def test_curated_pending_query_then_completed_poll_can_pass(self) -> None:
        result, _, _ = self.run_responses([response(
            call(output='{"status":"ASKING_AI"}'),
            call(name="poll_response_space", output='{"status":"COMPLETED"}', id="call_2"),
            answer(),
        )])
        self.assertEqual(result, 0)

    def run_responses(self, responses: list[Mock], *, mode: str = "genie-agent", **options: bool):
        client = Mock()
        client.responses.create.side_effect = responses
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = run_smoke(client, mode, "synthetic-private-question", **options)
        return result, output.getvalue(), client

    def test_requires_real_completed_tool_call_and_answer(self) -> None:
        result, output, client = self.run_responses([response(call(), answer())])
        self.assertEqual(result, 0)
        for marker in ("synthetic-private-question", "synthetic-private-answer", "synthetic-private-result"):
            self.assertNotIn(marker, output)
        request = client.responses.create.call_args.kwargs
        self.assertNotIn("extra_body", request)
        self.assertNotIn("previous_response_id", request)
        self.assertEqual(request["tool_choice"], "required")
        self.assertFalse(request["parallel_tool_calls"])
        self.assertIn("permission isolation remain NOT VERIFIED", output)

    def test_plain_answer_discovery_and_incomplete_results_never_pass(self) -> None:
        cases = [
            response(answer()),
            response({"type": "mcp_list_tools", "tools": []}, answer()),
            response(call()),
            response(call(output=""), answer()),
            response(call(id=None), answer()),
            response(call(status="in_progress"), answer()),
            response(call(), answer(), status="incomplete"),
            response(call(), answer(), error={"message": "secret-canary"}),
            response(call(), answer(), id=None),
        ]
        for case in cases:
            with self.subTest(case=case):
                result, output, _ = self.run_responses([case])
                self.assertEqual(result, 4)
                self.assertNotIn("PASS:", output)
                self.assertNotIn("secret-canary", output)

    def test_protocol_and_structured_tool_errors_fail(self) -> None:
        cases = [
            call(error={"message": "secret-canary"}),
            call(status="failed"),
            call(output='{"isError":true,"content":[]}'),
            call(output='{"structuredContent":{"status":"failed"}}'),
            call(output=json.dumps({"content": [{
                "type": "text", "text": '{"error":{"code":"CONSENT_REQUIRED"}}'
            }]})),
        ]
        for item in cases:
            with self.subTest(item=item):
                result, output, _ = self.run_responses([response(item, answer())])
                self.assertEqual(result, 4)
                self.assertNotIn("secret-canary", output)

    def test_genie_one_requires_completed_poll_not_just_started_query(self) -> None:
        started = call(name="genie_ask", output='{"status":"in_progress"}')
        result, _, _ = self.run_responses([response(started, answer())], mode="genie-one")
        self.assertEqual(result, 4)
        for payload in (
            {"status": "completed"},
            {"structuredContent": {"status": "completed"}},
            {"content": [{"type": "text", "text": '{"status":"completed"}'}]},
        ):
            result, _, _ = self.run_responses([
                response(call(name="genie_poll_response", output=json.dumps(payload)), answer())
            ], mode="genie-one")
            self.assertEqual(result, 0)

    def test_noninteractive_consent_exits_without_opening_or_printing_link(self) -> None:
        consent = {
            "type": "oauth_consent_request",
            "consent_link": "https://login.example/authorize?code=sensitive-canary",
        }
        with patch("foundry_databricks_genie.smoke.webbrowser.open") as browser:
            result, output, _ = self.run_responses([response(consent)], non_interactive=True)
        self.assertEqual(result, 3)
        self.assertNotIn("sensitive-canary", output)
        browser.assert_not_called()

    def test_consent_retries_same_response_only_after_user_confirmation(self) -> None:
        consent = {"type": "oauth_consent_request", "consent_link": "https://login.example/authorize"}
        with patch("foundry_databricks_genie.smoke._consent", return_value=True):
            result, _, client = self.run_responses([
                response(consent, status="incomplete"), response(call(), answer()),
            ])
        self.assertEqual(result, 0)
        second = client.responses.create.call_args_list[1].kwargs
        self.assertEqual(second["previous_response_id"], "resp_1")
        self.assertEqual(second["input"], "synthetic-private-question")

    def test_browser_open_is_not_itself_success(self) -> None:
        consent = {"type": "oauth_consent_request", "consent_link": "https://login.example/authorize"}
        with patch("foundry_databricks_genie.smoke._consent", return_value=True):
            result, _, client = self.run_responses([response(consent)] * MAX_ROUNDS)
        self.assertEqual(result, 4)
        self.assertEqual(client.responses.create.call_count, MAX_ROUNDS)

    def test_rejects_unsafe_consent_urls(self) -> None:
        for url in (
            None, "http://login.example", "file:///local", "javascript:alert(1)",
            "https://user:password@login.example", "https://login.example\n/sensitive",
            "https://[broken", "https://login.example:invalid", "https://login.example\\other",
        ):
            with self.subTest(url=url), self.assertRaises(ConfigurationError):
                _consent(url, True)

    def test_declined_browser_prompt_does_not_open_link(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            with patch("builtins.input", return_value="n"), patch("webbrowser.open") as browser:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(_consent("https://login.example/authorize", False))
        browser.assert_not_called()

    def test_tool_approvals_require_explicit_permission(self) -> None:
        approval = {"type": "mcp_approval_request", "id": "approval_1", "server_label": SERVER_LABEL}
        result, _, client = self.run_responses([response(approval)])
        self.assertEqual(result, 3)
        self.assertEqual(client.responses.create.call_count, 1)
        result, _, client = self.run_responses([
            response(approval), response(call(), answer())
        ], approve_tools=True)
        self.assertEqual(result, 0)
        self.assertEqual(client.responses.create.call_args.kwargs["input"], [{
            "type": "mcp_approval_response", "approval_request_id": "approval_1", "approve": True,
        }])

    def test_unexpected_tool_or_approval_server_is_rejected(self) -> None:
        for item in (
            call(server_label="unrelated"),
            {"type": "mcp_approval_request", "id": "approval_1", "server_label": "unrelated"},
        ):
            with self.assertRaises(ConfigurationError):
                self.run_responses([response(item)], approve_tools=True)

    def test_question_file_bounds_and_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "question.txt"
            for value in ("", " \n ", "bad\x00value", "x" * 32769):
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ConfigurationError):
                    read_question(path)
            path.write_text("test question", encoding="utf-8-sig")
            self.assertEqual(read_question(path), "test question")
            path.write_text("x" * 32768, encoding="utf-8")
            self.assertEqual(len(read_question(path)), 32768)


if __name__ == "__main__":
    unittest.main()
