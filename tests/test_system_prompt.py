from __future__ import annotations

import unittest
from pathlib import Path


class SystemPromptTests(unittest.TestCase):
    def test_prompt_contains_cx_guardrails(self):
        prompt = Path("SYSTEM_PROMPT.md").read_text()

        self.assertIn("Do not give medical advice.", prompt)
        self.assertIn("Do not recommend cannabis products or dosing.", prompt)
        self.assertIn("Do not promise refunds, cancellations, edits, or inventory changes by email.", prompt)
