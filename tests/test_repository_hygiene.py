from __future__ import annotations

import re
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
}


class RepositoryHygieneTests(unittest.TestCase):
    def _repository_text(self) -> str:
        chunks: list[str] = []
        for path in ROOT.rglob("*"):
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
        self.assertFalse((ROOT / ".env").exists())

    def test_examples_use_placeholders(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("<foundry-account>", example)
        self.assertIn("<databricks-workspace>", example)
        self.assertIn("<genie-space-id>", example)


if __name__ == "__main__":
    unittest.main()
