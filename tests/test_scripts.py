from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="connector script ")
        self.addCleanup(self.directory.cleanup)
        self.env_file = Path(self.directory.name) / "invalid.env"
        self.env_file.write_text("FOUNDRY_PROJECT_ENDPOINT=\n", encoding="utf-8")
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("FOUNDRY_", "DATABRICKS_"))
        }
        self.environment["ENV_FILE"] = str(self.env_file)

    def bash(self) -> str:
        if os.name == "nt":
            git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
            if git_bash.exists():
                return str(git_bash)
        command = shutil.which("bash")
        if command is None:
            self.skipTest("Bash is not installed.")
        return command

    def test_bash_rejects_invalid_configuration_before_cloud_access(self) -> None:
        result = subprocess.run(
            [self.bash(), str(ROOT / "scripts" / "setup.sh")],
            cwd=self.directory.name, env=self.environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required configuration value: FOUNDRY_PROJECT_ENDPOINT", result.stderr)
        self.assertNotIn("Setup resource checks completed", result.stdout)

    def test_bash_rejects_extra_arguments(self) -> None:
        result = subprocess.run(
            [self.bash(), str(ROOT / "scripts" / "setup.sh"), "--replace-connection", "extra"],
            env=self.environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)

    def test_bootstrap_shell_entry_points_are_plan_only_by_default(self) -> None:
        self.env_file.write_text(
            "FOUNDRY_PROJECT_ENDPOINT=https://example.services.ai.azure.com/api/projects/demo\n"
            "DATABRICKS_WORKSPACE_HOST=https://example.azuredatabricks.net\n"
            "DATABRICKS_GENIE_SPACE_ID=space_123-abc\n"
            "FOUNDRY_CONNECTION_NAME=genie\nFOUNDRY_TOOLBOX_NAME=genie-toolbox\n"
            "FOUNDRY_TEST_AGENT_NAME=genie-test\nFOUNDRY_MODEL_DEPLOYMENT=existing-model\n",
            encoding="utf-8",
        )
        commands = [[self.bash(), str(ROOT / "scripts" / "setup.sh"), "--bootstrap"]]
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell:
            commands.append([
                powershell, "-NoProfile", "-NonInteractive", "-File",
                str(ROOT / "scripts" / "setup.ps1"), "-EnvFile", str(self.env_file), "-Bootstrap",
            ])
        for command in commands:
            with self.subTest(shell=command[0]):
                result = subprocess.run(
                    command, cwd=self.directory.name, env=self.environment,
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("PLAN ONLY", result.stdout)
                self.assertNotIn("Dedicated agent ready", result.stdout)

    def test_bootstrap_rejects_replacement_flag(self) -> None:
        result = subprocess.run(
            [self.bash(), str(ROOT / "scripts" / "setup.sh"), "--bootstrap", "--replace-connection"],
            env=self.environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_powershell_rejects_invalid_configuration_before_cloud_access(self) -> None:
        command = shutil.which("pwsh") or shutil.which("powershell")
        if command is None:
            self.skipTest("PowerShell is not installed.")
        result = subprocess.run(
            [command, "-NoProfile", "-NonInteractive", "-File",
             str(ROOT / "scripts" / "setup.ps1"), "-EnvFile", str(self.env_file)],
            cwd=self.directory.name, env=self.environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required configuration value: FOUNDRY_PROJECT_ENDPOINT", result.stderr)
        self.assertNotIn("Setup resource checks completed", result.stdout)


if __name__ == "__main__":
    unittest.main()
