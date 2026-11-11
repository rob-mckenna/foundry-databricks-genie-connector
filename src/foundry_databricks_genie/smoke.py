"""Bounded Responses API smoke tests; never print prompts, results or consent URLs."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .config import ConfigurationError

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types.responses import ResponseInputParam
    from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming


SERVER_LABEL = "genie_toolbox"
MAX_ROUNDS = 12


def read_question(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            data = stream.read(32_769)
        if len(data) > 32_768:
            raise ConfigurationError("The smoke-test question must be at most 32 KiB.")
        question = data.decode("utf-8-sig").strip()
    except (OSError, UnicodeError) as error:
        raise ConfigurationError("Could not read the UTF-8 smoke-test question file.") from error
    if not question or "\x00" in question:
        raise ConfigurationError("The smoke-test question must be nonempty text without NUL.")
    return question


def _consent(url: object, non_interactive: bool) -> bool:
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        raise ConfigurationError("Foundry returned an invalid consent link.")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as error:
        raise ConfigurationError("Foundry returned an invalid consent link.") from error
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.fragment or "\\" in url or port == 0
    ):
        raise ConfigurationError("Foundry returned an unsafe consent link.")
    if non_interactive or not sys.stdin.isatty() or not sys.stdout.isatty():
        print("NEEDS_CONSENT: complete OAuth in the Foundry playground or rerun interactively.")
        return False
    print(f"OAuth consent is requested at HTTPS host: {parsed.hostname}")
    try:
        if input("Open this consent page in your browser? [y/N] ").strip().lower() != "y":
            return False
        try:
            opened = webbrowser.open(url, new=2)
        except webbrowser.Error:
            opened = False
        if not opened:
            print("NEEDS_CONSENT: browser could not be opened; use the Foundry playground.")
            return False
        return input(
            "Complete sign-in and consent, then press Enter to retry (q to stop): "
        ).strip().lower() != "q"
    except EOFError:
        print("NEEDS_CONSENT: interactive input ended; no consent completion assumed.")
        return False


def _payloads(output: str) -> list[dict[str, object]]:
    """Unwrap documented MCP envelopes, not arbitrary business-data fields."""
    if len(output) > 4_194_304:
        raise ConfigurationError("Tool output exceeded the smoke-test inspection limit.")
    remaining = output.strip()
    result: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    # Foundry can concatenate a text JSON block and a structuredResponse block.
    while remaining:
        if len(result) >= 64:
            raise ConfigurationError("Tool output exceeded the JSON-block inspection limit.")
        try:
            value, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError:
            if result:
                raise ConfigurationError("Tool output contains a malformed trailing JSON block.")
            return []
        remaining = remaining[end:].lstrip()
        if not isinstance(value, dict):
            continue
        result.append(value)
        for key in ("structuredContent", "structuredResponse"):
            structured = value.get(key)
            if isinstance(structured, dict):
                result.append(structured)
        content = value.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        try:
                            decoded: object = json.loads(text)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(decoded, dict):
                            result.append(decoded)
    return result


def run_smoke(
    client: OpenAI,
    mode: str,
    question: str,
    *,
    approve_tools: bool = False,
    non_interactive: bool = False,
    server_label: str = SERVER_LABEL,
) -> int:
    previous_id: str | None = None
    request_input: str | ResponseInputParam = question
    completed_calls: set[str] = set()
    genie_one_completed = False
    genie_query_pending = False
    for _ in range(MAX_ROUNDS):
        request: ResponseCreateParamsNonStreaming = {
            "input": request_input,
            "tool_choice": "required" if previous_id is None else "auto",
            "parallel_tool_calls": False,
            "max_output_tokens": 4096,
            "store": True,
        }
        if previous_id is not None:
            request["previous_response_id"] = previous_id
        response = client.responses.create(**request)
        # Foundry extension items can trigger SDK serialization warnings containing
        # signed consent URLs. Validate the resulting fields below without logging them.
        document = response.model_dump(mode="json", warnings=False)
        status = document.get("status")
        output = document.get("output")
        response_id = document.get("id")
        if (
            document.get("error") or status in ("failed", "cancelled")
            or not isinstance(output, list)
            or not isinstance(response_id, str) or not response_id
        ):
            print("FAIL: invalid or failed agent response; inspect details privately in Foundry.")
            return 4
        consent_items = []
        approval_items = []
        has_answer = False
        for item in output:
            if not isinstance(item, dict):
                raise ConfigurationError("Foundry returned an invalid response output item.")
            kind = item.get("type")
            if kind == "oauth_consent_request":
                consent_items.append(item)
            elif kind == "mcp_approval_request":
                approval_items.append(item)
            elif kind == "message" and item.get("role") == "assistant":
                content = item.get("content")
                has_answer |= isinstance(content, list) and any(
                    isinstance(part, dict) and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str) and bool(part["text"].strip())
                    for part in content
                )
            elif kind == "mcp_call":
                if item.get("server_label") != server_label:
                    raise ConfigurationError("An unexpected MCP server appeared in the test response.")
                if item.get("error") or item.get("status") == "failed":
                    print("FAIL: an MCP call failed; no tool payload was printed.")
                    return 4
                value = item.get("output")
                call_id = item.get("id")
                if item.get("status") == "completed" and isinstance(value, str) and value.strip():
                    payloads = _payloads(value)
                    if any(
                        p.get("isError") is True or p.get("error")
                        or str(p.get("status", "")).lower() in (
                            "failed", "incomplete", "cancelled", "canceled"
                        )
                        for p in payloads
                    ):
                        print("FAIL: the MCP result reports an error or unsuccessful operation.")
                        return 4
                    if isinstance(call_id, str) and call_id:
                        completed_calls.add(call_id)
                    name = item.get("name")
                    if mode == "genie-agent" and isinstance(name, str) and (
                        "query_space" in name or "poll_response" in name
                    ):
                        statuses = {
                            query_status.lower() for p in payloads
                            if isinstance(query_status := p.get("status"), str)
                        }
                        if statuses:
                            genie_query_pending = statuses != {"completed"}
                    if (
                        isinstance(name, str) and name.endswith("genie_poll_response")
                        and any(p.get("status") == "completed" for p in payloads)
                    ):
                        genie_one_completed = True
        if consent_items and approval_items:
            raise ConfigurationError(
                "Consent and tool approval arrived together; review this response in the playground."
            )
        if consent_items:
            for item in consent_items:
                if not _consent(item.get("consent_link"), non_interactive):
                    print("NOT VERIFIED: OAuth consent was not confirmed by a successful retry.")
                    return 3
            previous_id = response_id
            request_input = question
            continue
        if approval_items:
            if not approve_tools:
                print(
                    "NEEDS_TOOL_APPROVAL: review tool arguments in the playground, "
                    "or rerun with --approve-tools to authorize this smoke test's Toolbox calls."
                )
                return 3
            approvals: ResponseInputParam = []
            for item in approval_items:
                approval_id = item.get("id")
                if item.get("server_label") != server_label or not isinstance(approval_id, str):
                    raise ConfigurationError("Foundry returned an invalid tool approval request.")
                approvals.append({
                    "type": "mcp_approval_response",
                    "approval_request_id": approval_id,
                    "approve": True,
                })
            previous_id = response_id
            request_input = approvals
            continue
        if status != "completed" or not has_answer or not completed_calls:
            print("NOT VERIFIED: a completed tool call and final agent answer were not both observed.")
            return 4
        if mode == "genie-one" and not genie_one_completed:
            print("NOT VERIFIED: no structured completed Genie One polling result was observed.")
            return 4
        if genie_query_pending:
            print("NOT VERIFIED: the curated Genie query has not reached completed status.")
            return 4
        print(f"OBSERVED: {len(completed_calls)} completed MCP call(s) and a final agent answer.")
        print("Data correctness, effective identity and permission isolation remain NOT VERIFIED.")
        return 0
    print("NOT VERIFIED: smoke-test response limit reached; inspect ongoing work in Foundry.")
    return 4
