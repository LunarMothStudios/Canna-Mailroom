from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.cx_models import KnowledgeAnswer, OrderLookupResult, ProviderConfigurationError
from app.cx_providers import BridgeOrderProvider, JaneOrderProvider, TreezOrderProvider, load_knowledge_provider, load_order_provider
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

    def make_treez_private_key_file(self) -> str:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path = Path(temp_dir.name) / "treez-private.pem"
        path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
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
            order_provider_factory=f"{__name__}:build_custom_provider",
        )

        provider = load_order_provider(settings)

        self.assertEqual(provider.lookup("1001").to_tool_output()["source"], "custom")

    def test_invalid_custom_provider_is_rejected(self):
        settings = SimpleNamespace(
            order_provider="custom",
            order_provider_factory=f"{__name__}:build_invalid_provider",
        )

        with self.assertRaises(ProviderConfigurationError):
            load_order_provider(settings)

    def test_load_treez_provider(self):
        settings = SimpleNamespace(
            order_provider="treez",
            treez_dispensary="downtown-cannabis",
            treez_organization_id="org-123",
            treez_certificate_id="cert-abc",
            treez_private_key_file=self.make_treez_private_key_file(),
            treez_api_base_url="https://api-prod.treez.io",
        )

        provider = load_order_provider(settings)

        self.assertIsInstance(provider, TreezOrderProvider)

    def test_load_jane_provider(self):
        settings = SimpleNamespace(
            order_provider="jane",
            jane_bridge_url="https://bridge.example.com/jane",
            jane_bridge_token="secret",
            jane_bridge_timeout_seconds=20,
        )

        provider = load_order_provider(settings)

        self.assertIsInstance(provider, JaneOrderProvider)

    def test_load_bridge_provider(self):
        settings = SimpleNamespace(
            order_provider="bridge",
            bridge_order_provider_url="https://bridge.example.com/orders",
            bridge_order_provider_token="secret",
            bridge_order_provider_source="flowhub",
            bridge_order_provider_timeout_seconds=12,
        )

        provider = load_order_provider(settings)

        self.assertIsInstance(provider, BridgeOrderProvider)
