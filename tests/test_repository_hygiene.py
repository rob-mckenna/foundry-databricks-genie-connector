from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    "",
    ".example",
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
    ".template",
}


class RepositoryHygieneTests(unittest.TestCase):
    def _repository_text(self) -> str:
        chunks: list[str] = []
        tracked = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT, check=True, capture_output=True
        ).stdout.decode("utf-8").split("\0")
        for relative in tracked:
            if not relative:
                continue
            path = ROOT / relative
            if not path.is_file():
                continue
            if any(part in {".git", ".generated", "__pycache__"} for part in path.parts):
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        return "\n".join(chunks)

    def test_no_common_token_prefixes_or_bearer_values(self) -> None:
        text = self._repository_text()
        patterns = (
            r"ghp" r"_[A-Za-z0-9]{20,}",
            r"github" r"_pat_[A-Za-z0-9_]{20,}",
            r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}",
            r"(?i)(client_secret|api_key|access_token)\s*=\s*[\"'][^<${][^\"']+",
        )
        for pattern in patterns:
            self.assertIsNone(re.search(pattern, text), pattern)

    def test_no_local_environment_file_is_tracked(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        )
        tracked = result.stdout.decode("utf-8").split("\0")
        forbidden = [
            name for name in tracked
            if Path(name).name == ".env"
            or (Path(name).name.startswith(".env.") and Path(name).name != ".env.example")
            or name.startswith(".generated/")
        ]
        self.assertEqual(forbidden, [], "Local configuration or generated state is tracked.")

    def test_local_configuration_is_ignored(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", ".env", ".env.local",
             ".generated/toolbox.yaml"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        self.assertEqual(len(result.stdout.splitlines()), 3)

    def test_examples_use_placeholders(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("<foundry-account>", example)
        self.assertIn("<databricks-workspace>", example)
        self.assertIn("<genie-space-id>", example)


if __name__ == "__main__":
    unittest.main()
