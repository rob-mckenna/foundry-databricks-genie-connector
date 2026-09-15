"""Offline configuration commands used by the setup scripts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .config import ConfigurationError, load_configuration


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

    subparsers.add_parser("preflight")
    return parser


def _render_toolbox(connection_name: str) -> str:
    return (
        "description: Azure Databricks Genie tools exposed through a managed "
        "Foundry Toolbox.\n"
        "connections:\n"
        f"  - name: {connection_name}\n"
    )


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def _values_for_keys(value: object, accepted_keys: set[str]) -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if _normalized_key(str(key)) in accepted_keys and isinstance(child, str):
                matches.append(child)
            matches.extend(_values_for_keys(child, accepted_keys))
    elif isinstance(value, list):
        for child in value:
            matches.extend(_values_for_keys(child, accepted_keys))
    return matches


def _load_json(path: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"Could not read JSON from {path}: {error}") from error


def _assert_connection(path: str, expected_name: str, expected_target: str) -> None:
    document = _load_json(path)
    names = _values_for_keys(document, {"name", "connectionname"})
    targets = _values_for_keys(document, {"target", "targeturl", "serverurl"})

    if names and expected_name not in names:
        raise ConfigurationError(
            "The existing project connection name does not match the configuration."
        )
    normalized_target = expected_target.rstrip("/")
    if normalized_target not in {target.rstrip("/") for target in targets}:
        raise ConfigurationError(
            "The existing project connection targets a different MCP endpoint. "
            "Use the explicit replace option after confirming the resource."
        )


def _assert_toolbox_connections(path: str, expected_name: str) -> None:
    document = _load_json(path)
    names = _values_for_keys(document, {"name", "connectionname"})
    if expected_name not in names:
        raise ConfigurationError(
            "The existing Toolbox does not reference the configured project "
            "connection. Choose a different Toolbox name or reconcile it manually."
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preflight":
            missing = [
                command for command in ("python", "azd") if shutil.which(command) is None
            ]
            if missing:
                raise ConfigurationError(
                    "Missing required command(s): " + ", ".join(missing)
                )
            print("Required local commands are available.")
            return 0

        if args.command == "assert-connection":
            _assert_connection(
                args.input,
                args.expected_name,
                args.expected_target,
            )
            print("Existing project connection matches the configuration.")
            return 0

        if args.command == "assert-toolbox-connections":
            _assert_toolbox_connections(args.input, args.expected_name)
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
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                _render_toolbox(configuration.foundry_connection_name),
                encoding="utf-8",
            )
            print(f"Rendered Toolbox configuration: {output}")
        return 0
    except ConfigurationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
