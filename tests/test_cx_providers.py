from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.cx_models import ProviderAPIError
from app.cx_providers import (
    BridgeOrderProvider,
    DutchieOrderProvider,
    JaneOrderProvider,
    ManualKnowledgeProvider,
    ManualOrderProvider,
    TreezOrderProvider,
)


STORE_KNOWLEDGE = {
    "brand": {
        "support_phone": "(555) 010-4200",
        "support_email": "support@example.com",
    },
    "locations": [
        {
            "id": "downtown",
            "name": "Downtown",
            "aliases": ["main street"],
            "hours": {"daily": "9 AM - 9 PM"},
            "payment_methods": ["Cash", "Debit"],
            "supports_medical": True,
            "supports_adult_use": True,
            "id_requirements": ["Bring a valid government-issued photo ID."],
            "pickup_notes": "Pickup orders are held until close.",
            "delivery_notes": "Delivery runs from noon to 6 PM.",
            "contact_phone": "(555) 111-2222",
        },
        {
            "id": "northside",
            "name": "Northside",
            "aliases": ["uptown"],
            "hours": {"daily": "10 AM - 8 PM"},
            "payment_methods": ["Cash", "Debit", "CanPay"],
            "supports_medical": True,
            "supports_adult_use": True,
            "id_requirements": ["Bring a valid government-issued photo ID."],
            "pickup_notes": "Pickup orders are held for two hours after ready.",
            "delivery_notes": "Northside does not deliver.",
            "contact_phone": "(555) 333-4444",
        },
    ],
    "policies": {
        "cancellation": "The email agent cannot cancel or edit orders.",
        "refund": "Refunds are handled by the store directly.",
    },
    "faq_entries": [
        {
            "id": "faq-id",
            "topic": "id_requirements",
            "question": "What ID do I need?",
            "answer": "Bring a valid government-issued photo ID.",
            "keywords": ["id", "license", "medical card"],
        }
    ],
}


MANUAL_ORDERS = {
    "orders": [
        {
            "order_number": "A100",
            "customer_email": "alex@example.com",
            "phone_last4": "4242",
            "status": "Ready for pickup",
            "fulfillment_type": "Pickup",
            "location_name": "Downtown",
            "ready_window": "Ready now until close.",
            "payment_summary": "Estimated total: $48.75. Pay in store.",
            "notes": ["Bring a valid photo ID."],
        }
    ]
}


class ProviderFixtureMixin:
    def make_json_file(self, payload: dict) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "data.json"
        path.write_text(json.dumps(payload))
        return str(path)


class ManualKnowledgeProviderTests(ProviderFixtureMixin, unittest.TestCase):
    def test_exact_location_match_returns_hours_answer(self):
        provider = ManualKnowledgeProvider(self.make_json_file(STORE_KNOWLEDGE))

        result = provider.search("What are your hours?", location_hint="Downtown")

        self.assertEqual(result.to_tool_output()["status"], "found")
        self.assertEqual(result.to_tool_output()["matched_topic"], "hours")
        self.assertEqual(result.to_tool_output()["matched_location"], "Downtown")

    def test_keyword_match_returns_general_id_answer(self):
        provider = ManualKnowledgeProvider(self.make_json_file(STORE_KNOWLEDGE))

        result = provider.search("What ID do I need to shop?")

        self.assertEqual(result.to_tool_output()["status"], "found")
        self.assertEqual(result.to_tool_output()["matched_topic"], "id_requirements")

    def test_location_sensitive_questions_without_location_are_ambiguous(self):
        provider = ManualKnowledgeProvider(self.make_json_file(STORE_KNOWLEDGE))

        result = provider.search("Are you open tonight?")

        self.assertEqual(result.to_tool_output()["status"], "ambiguous")
        self.assertIn("Downtown", result.to_tool_output()["options"])
        self.assertIn("Northside", result.to_tool_output()["options"])

    def test_unknown_question_returns_contact_guidance(self):
        provider = ManualKnowledgeProvider(self.make_json_file(STORE_KNOWLEDGE))

        result = provider.search("Do you validate parking?")

        self.assertEqual(result.to_tool_output()["status"], "not_found")
        self.assertIn("contact", result.to_tool_output()["follow_up"].lower())


class ManualOrderProviderTests(ProviderFixtureMixin, unittest.TestCase):
    def test_successful_lookup_returns_found_result(self):
        provider = ManualOrderProvider(self.make_json_file(MANUAL_ORDERS))

        result = provider.lookup("A100", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["order_status"], "Ready for pickup")

    def test_missing_order_returns_not_found(self):
        provider = ManualOrderProvider(self.make_json_file(MANUAL_ORDERS))

        result = provider.lookup("missing")

        self.assertEqual(result.to_tool_output()["status"], "not_found")

    def test_identity_mismatch_is_reported(self):
        provider = ManualOrderProvider(self.make_json_file(MANUAL_ORDERS))

        result = provider.lookup("A100", customer_email="someoneelse@example.com")

        self.assertEqual(result.to_tool_output()["status"], "identity_mismatch")


class DutchieOrderProviderTests(unittest.TestCase):
    def make_provider(self) -> DutchieOrderProvider:
        return DutchieOrderProvider("location-key", "integrator-key")

    def test_successful_lookup_maps_status_payload(self):
        provider = self.make_provider()

        def side_effect(method, path, **kwargs):
            if (method, path) == ("GET", "/preorder/Status"):
                return [
                    {
                        "preOrderId": 80245,
                        "status": "Accepted",
                        "customerId": 123,
                        "orderType": "Pickup",
                        "orderDate": "2026-03-14T15:10:00Z",
                        "total": 87.5,
                        "isCancellable": True,
                        "isUpdateable": True,
                    }
                ]
            if (method, path) == ("POST", "/customer/customerLookup"):
                return {"customerId": 123}
            if (method, path) == ("GET", "/whoami"):
                return {"locationId": 44, "locationName": "Downtown"}
            raise AssertionError(f"Unexpected Dutchie call: {(method, path)}")

        provider._request_json = Mock(side_effect=side_effect)

        result = provider.lookup("80245", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["location_name"], "Downtown")
        self.assertIn("Matched the sender email", payload["verification_summary"])

    def test_not_found_when_preorder_status_is_empty(self):
        provider = self.make_provider()
        provider._request_json = Mock(return_value=[])

        result = provider.lookup("80245")

        self.assertEqual(result.to_tool_output()["status"], "not_found")

    def test_identity_mismatch_when_customer_lookup_points_elsewhere(self):
        provider = self.make_provider()

        def side_effect(method, path, **kwargs):
            if (method, path) == ("GET", "/preorder/Status"):
                return [{"preOrderId": 80245, "status": "Accepted", "customerId": 123}]
            if (method, path) == ("POST", "/customer/customerLookup"):
                return {"customerId": 999}
            raise AssertionError(f"Unexpected Dutchie call: {(method, path)}")

        provider._request_json = Mock(side_effect=side_effect)

        result = provider.lookup("80245", customer_email="alex@example.com")

        self.assertEqual(result.to_tool_output()["status"], "identity_mismatch")

    def test_verification_is_blocked_when_customer_lookup_is_forbidden(self):
        provider = self.make_provider()

        def side_effect(method, path, **kwargs):
            if (method, path) == ("GET", "/preorder/Status"):
                return [{"preOrderId": 80245, "status": "Accepted", "customerId": 123}]
            if (method, path) == ("POST", "/customer/customerLookup"):
                raise ProviderAPIError("forbidden", status_code=403)
            raise AssertionError(f"Unexpected Dutchie call: {(method, path)}")

        provider._request_json = Mock(side_effect=side_effect)

        result = provider.lookup("80245", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "identity_mismatch")
        self.assertIn("permission scopes", payload["verification_summary"])

    def test_verification_is_blocked_when_order_has_no_customer_id(self):
        provider = self.make_provider()

        def side_effect(method, path, **kwargs):
            if (method, path) == ("GET", "/preorder/Status"):
                return [{"preOrderId": 80245, "status": "Accepted"}]
            if (method, path) == ("POST", "/customer/customerLookup"):
                return {"customerId": 123}
            raise AssertionError(f"Unexpected Dutchie call: {(method, path)}")

        provider._request_json = Mock(side_effect=side_effect)

        result = provider.lookup("80245", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "identity_mismatch")
        self.assertIn("did not expose a customer id", payload["verification_summary"])

    def test_raises_for_auth_rate_limit_and_upstream_failures(self):
        for status_code in (401, 403, 429, 500):
            provider = self.make_provider()
            provider._request_json = Mock(side_effect=ProviderAPIError("boom", status_code=status_code))
            with self.subTest(status_code=status_code):
                with self.assertRaises(ProviderAPIError) as ctx:
                    provider.lookup("80245")
                self.assertEqual(ctx.exception.status_code, status_code)


class BridgeOrderProviderTests(unittest.TestCase):
    def test_bridge_payload_maps_to_found_result(self):
        provider = BridgeOrderProvider("https://bridge.example.com/orders", auth_token="secret", source="bridge")
        provider._headers = Mock(return_value={"Accept": "application/json", "Authorization": "Bearer secret"})

        with patch("app.cx_providers._request_json_url", return_value={
            "status": "found",
            "order_number": "B100",
            "order_status": "Ready",
            "fulfillment_type": "Delivery",
            "location_name": "Northside",
            "customer_safe_notes": ["Driver is en route."],
        }):
            result = provider.lookup("B100", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["source"], "bridge")
        self.assertEqual(payload["order_status"], "Ready")

    def test_bridge_payload_without_explicit_found_status_is_rejected(self):
        provider = BridgeOrderProvider("https://bridge.example.com/orders", source="bridge")

        with patch("app.cx_providers._request_json_url", return_value={"order_number": "B100"}):
            with self.assertRaises(ProviderAPIError):
                provider.lookup("B100")

    def test_bridge_404_maps_to_not_found(self):
        provider = BridgeOrderProvider("https://bridge.example.com/orders", source="bridge")

        with patch(
            "app.cx_providers._request_json_url",
            side_effect=ProviderAPIError("missing", status_code=404),
        ):
            result = provider.lookup("B404")

        self.assertEqual(result.to_tool_output()["status"], "not_found")


class JaneOrderProviderTests(unittest.TestCase):
    def test_jane_provider_uses_bridge_contract(self):
        provider = JaneOrderProvider("https://jane-bridge.example.com", "token", 20)

        with patch("app.cx_providers._request_json_url", return_value={
            "status": "found",
            "order_number": "J100",
            "order_status": "Accepted",
        }):
            result = provider.lookup("J100")

        self.assertEqual(result.to_tool_output()["source"], "jane")


class TreezOrderProviderTests(unittest.TestCase):
    def make_provider(self) -> TreezOrderProvider:
        return TreezOrderProvider(
            dispensary="downtown-cannabis",
            client_id="client-123",
            api_key="api-key",
        )

    def test_lookup_fetches_access_token_and_calls_v2_ticket_endpoint(self):
        provider = self.make_provider()

        with patch(
            "app.cx_providers._request_json_path",
            side_effect=[
                {"access_token": "treez-token", "expires_in": 7200},
                {
                    "resultCode": "SUCCESS",
                    "data": {
                        "order_number": "1001",
                        "order_status": "ready_for_pickup",
                        "type": "pickup",
                        "location_name": "Downtown",
                        "date_created": "2026-03-14T15:10:00Z",
                        "scheduled_date": "2026-03-14T16:00:00Z",
                        "payment_status": "unpaid",
                        "total": 87.5,
                        "ticket_note": "Bring a government-issued photo ID.",
                        "customer_email": "alex@example.com",
                        "phone": "(555) 555-4242",
                    },
                },
            ],
        ) as request_mock:
            result = provider.lookup("1001", customer_email="alex@example.com", phone_last4="4242")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["source"], "treez")
        self.assertIn("unpaid", payload["payment_summary"])
        self.assertIn("Matched the sender email", payload["verification_summary"])
        self.assertEqual(request_mock.call_args_list[0].args, ("https://api.treez.io", "/auth/v1/config/api/gettokens"))
        self.assertEqual(request_mock.call_args_list[0].kwargs["method"], "POST")
        self.assertEqual(
            request_mock.call_args_list[0].kwargs["body"],
            {"client_id": "client-123", "api_key": "api-key"},
        )
        self.assertEqual(
            request_mock.call_args_list[1].args,
            ("https://api.treez.io", "/v2.0/dispensary/downtown-cannabis/ticket/ordernumber/1001"),
        )
        self.assertEqual(
            request_mock.call_args_list[1].kwargs["headers"]["Authorization"],
            "Bearer treez-token",
        )

    def test_lookup_returns_not_found_for_404(self):
        provider = self.make_provider()

        def side_effect(base_url, path, **kwargs):
            if path == "/auth/v1/config/api/gettokens":
                return {"access_token": "treez-token"}
            raise ProviderAPIError("missing", status_code=404)

        with patch("app.cx_providers._request_json_path", side_effect=side_effect):
            result = provider.lookup("missing")

        self.assertEqual(result.to_tool_output()["status"], "not_found")

    def test_lookup_returns_identity_mismatch_for_email_conflict(self):
        provider = self.make_provider()

        def side_effect(base_url, path, **kwargs):
            if path == "/auth/v1/config/api/gettokens":
                return {"access_token": "treez-token"}
            return {
                "resultCode": "SUCCESS",
                "data": {
                    "order_number": "1001",
                    "order_status": "accepted",
                    "customer_email": "someoneelse@example.com",
                },
            }

        with patch("app.cx_providers._request_json_path", side_effect=side_effect):
            result = provider.lookup("1001", customer_email="alex@example.com")

        self.assertEqual(result.to_tool_output()["status"], "identity_mismatch")

    def test_lookup_returns_identity_mismatch_when_ticket_has_no_email_for_verification(self):
        provider = self.make_provider()

        def side_effect(base_url, path, **kwargs):
            if path == "/auth/v1/config/api/gettokens":
                return {"access_token": "treez-token"}
            return {
                "resultCode": "SUCCESS",
                "data": {
                    "order_number": "1001",
                    "order_status": "accepted",
                },
            }

        with patch("app.cx_providers._request_json_path", side_effect=side_effect):
            result = provider.lookup("1001", customer_email="alex@example.com")

        payload = result.to_tool_output()
        self.assertEqual(payload["status"], "identity_mismatch")
        self.assertIn("stable email field", payload["verification_summary"])
