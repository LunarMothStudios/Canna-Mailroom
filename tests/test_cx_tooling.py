from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.cx_models import KnowledgeAnswer, OrderLookupResult, ProviderConfigurationError
from app.cx_providers import load_knowledge_provider, load_order_provider
from app.cx_toolset import DispensaryCxToolset


def build_custom_provider(_settings=None):
    return CustomOrderProvider()


def build_invalid_provider(_settings=None):
    return object()


class CustomOrderProvider:
    def lookup(self, order_number: str, *, customer_email: str | None = None, phone_last4: str | None = None):
        return OrderLookupResult(
            order_number=order_number,
            order_status="Accepted",
            fulfillment_type="Pickup",
            location_name="Custom Shop",
            customer_safe_notes=("custom",),
            source="custom",
        )


class StubKnowledgeProvider:
    def search(self, question: str, *, location_hint: str | None = None):
        return KnowledgeAnswer(
            answer=f"Answer for {question}",
            matched_topic="faq",
            matched_location=location_hint,
            source_ids=("knowledge:1",),
        )


class DispensaryCxToolsetTests(unittest.TestCase):
    def test_specs_are_stable(self):
        toolset = DispensaryCxToolset(order_provider=CustomOrderProvider(), knowledge_provider=StubKnowledgeProvider())

        specs = toolset.specs()

        self.assertEqual([item["name"] for item in specs], ["lookup_order", "search_store_knowledge"])

    def test_run_dispatches_to_both_providers(self):
        toolset = DispensaryCxToolset(order_provider=CustomOrderProvider(), knowledge_provider=StubKnowledgeProvider())

        order_payload = toolset.run("lookup_order", {"order_number": "1001", "customer_email": "alex@example.com"})
        knowledge_payload = toolset.run(
            "search_store_knowledge",
            {"question": "What are your hours?", "location_hint": "Downtown"},
        )

        self.assertEqual(order_payload["status"], "found")
        self.assertEqual(order_payload["order_number"], "1001")
        self.assertEqual(knowledge_payload["status"], "found")
        self.assertEqual(knowledge_payload["matched_location"], "Downtown")


class ProviderLoadingTests(unittest.TestCase):
    def make_json_file(self, payload: dict) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "data.json"
        path.write_text(json.dumps(payload))
        return str(path)

    def test_load_manual_providers(self):
        settings = SimpleNamespace(
            order_provider="manual",
            knowledge_provider="manual",
            manual_order_file=self.make_json_file({"orders": [{"order_number": "1001", "status": "Ready"}]}),
            store_knowledge_file=self.make_json_file(
                {
                    "brand": {"support_phone": "(555) 000-0000"},
                    "locations": [{"id": "main", "name": "Main", "hours": {"daily": "9 AM - 9 PM"}}],
                    "faq_entries": [],
                    "policies": {},
                }
            ),
        )

        order_provider = load_order_provider(settings)
        knowledge_provider = load_knowledge_provider(settings)

        self.assertEqual(order_provider.lookup("1001").to_tool_output()["status"], "found")
        self.assertEqual(knowledge_provider.search("What are your hours?", location_hint="Main").to_tool_output()["status"], "found")

    def test_load_custom_provider_from_factory(self):
        settings = SimpleNamespace(
            order_provider="custom",
            order_provider_factory="test_cx_tooling:build_custom_provider",
        )

        provider = load_order_provider(settings)

        self.assertEqual(provider.lookup("1001").to_tool_output()["source"], "custom")

    def test_invalid_custom_provider_is_rejected(self):
        settings = SimpleNamespace(
            order_provider="custom",
            order_provider_factory="test_cx_tooling:build_invalid_provider",
        )

        with self.assertRaises(ProviderConfigurationError):
            load_order_provider(settings)
