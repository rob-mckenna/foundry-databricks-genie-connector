"""Offline configuration commands and explicit Foundry resource setup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigurationError, load_bootstrap_configuration, load_configuration, load_test_agent_name
from .setup import (
    assert_connection,
    assert_toolbox_connections,
    parse_json,
    preflight,
    setup,
    write_toolbox,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and render a Foundry to Databricks Genie setup."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("validate", "config", "endpoint"):
        child = subparsers.add_parser(command)
        child.add_argument("--env-file", default=".env")

    render = subparsers.add_parser("render-toolbox")
    render.add_argument("--env-file", default=".env")
    render.add_argument("--output", required=True)

    connection = subparsers.add_parser("assert-connection")
    connection.add_argument("--input", required=True)
    connection.add_argument("--expected-name", required=True)
    connection.add_argument("--expected-target", required=True)

    toolbox = subparsers.add_parser("assert-toolbox-connections")
    toolbox.add_argument("--input", required=True)
    toolbox.add_argument("--expected-name", required=True)

    provision = subparsers.add_parser("setup")
    provision.add_argument("--env-file", default=".env")
    provision.add_argument("--output", default=".generated/toolbox.yaml")
    provision.add_argument("--replace-connection", action="store_true")

    bootstrap = subparsers.add_parser(
        "bootstrap", help="Plan or apply dedicated test-agent setup; optionally run a smoke test."
    )
    bootstrap.add_argument("--env-file", default=".env")
    bootstrap.add_argument("--output", default=".generated/toolbox.yaml")
    bootstrap.add_argument("--apply", action="store_true")
    bootstrap.add_argument("--question-file")
    bootstrap.add_argument("--approve-tools", action="store_true")
    bootstrap.add_argument("--non-interactive", action="store_true")

    test_agent = subparsers.add_parser(
        "test-agent", help="Inspect and invoke an existing agent without provisioning."
    )
    test_agent.add_argument("--env-file", default=".env")
    test_agent.add_argument("--question-file", required=True)
    test_agent.add_argument("--approve-tools", action="store_true")
    test_agent.add_argument("--non-interactive", action="store_true")

    subparsers.add_parser("preflight")
    return parser


def _load_json(path: str) -> object:
    try:
        return parse_json(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError) as error:
        raise ConfigurationError("Could not read the JSON input file.") from error


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preflight":
            preflight()
            print("Required local commands are available.")
            return 0

        if args.command == "assert-connection":
            assert_connection(
                _load_json(args.input),
                args.expected_name,
                args.expected_target,
            )
            print("Existing project connection matches the configuration.")
            return 0

        if args.command == "assert-toolbox-connections":
            assert_toolbox_connections(_load_json(args.input), args.expected_name)
            print("Existing Toolbox references the configured connection.")
            return 0

        configuration = load_configuration(args.env_file)

        if args.command == "validate":
            print("Configuration is valid.")
        elif args.command == "config":
            print(json.dumps(configuration.to_dict(), sort_keys=True))
        elif args.command == "endpoint":
            print(configuration.genie_mcp_endpoint)
        elif args.command == "render-toolbox":
            output = Path(args.output)
            write_toolbox(output, configuration.foundry_connection_name)
            print(f"Rendered Toolbox configuration: {output}")
        elif args.command == "setup":
            setup(
                configuration, Path(args.output),
                replace_connection=args.replace_connection,
            )
        elif args.command == "test-agent":
            from .agent_test import execute_agent_test
            from .smoke import read_question

            agent_name = load_test_agent_name(args.env_file, configuration)
            question = read_question(Path(args.question_file))
            return execute_agent_test(
                configuration, agent_name, question,
                approve_tools=args.approve_tools, non_interactive=args.non_interactive,
            )
        elif args.command == "bootstrap":
            from .bootstrap import execute_bootstrap, print_plan
            from .smoke import read_question

            settings = load_bootstrap_configuration(args.env_file, configuration)
            question = read_question(Path(args.question_file)) if args.question_file else None
            if args.approve_tools and question is None:
                raise ConfigurationError("--approve-tools requires --question-file.")
            print_plan(configuration, settings)
            if not args.apply:
                print("PLAN ONLY: no cloud calls or file writes. Add --apply to execute.")
                return 0
            return execute_bootstrap(
                configuration, settings, Path(args.output), question,
                approve_tools=args.approve_tools, non_interactive=args.non_interactive,
            )
        return 0
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Inspect resource/query state before retrying.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
