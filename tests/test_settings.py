from __future__ import annotations

import unittest

from app.settings import normalize_sender_policy_mode


class SettingsTests(unittest.TestCase):
    def test_sender_policy_defaults_to_allowlist(self):
        self.assertEqual(normalize_sender_policy_mode(None), "allowlist")

    def test_invalid_sender_policy_falls_back_to_allowlist(self):
        self.assertEqual(normalize_sender_policy_mode("not-a-real-mode"), "allowlist")
