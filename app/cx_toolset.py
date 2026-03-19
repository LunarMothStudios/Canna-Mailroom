from __future__ import annotations

from typing import Any

from app.cx_models import AgentToolset, KnowledgeProvider, OrderProvider


class DispensaryCxToolset(AgentToolset):
    def __init__(self, order_provider: OrderProvider, knowledge_provider: KnowledgeProvider):
        self.order_provider = order_provider
        self.knowledge_provider = knowledge_provider

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": "lookup_order",
                "description": (
                    "Look up one dispensary order by order number and return customer-safe status details. "
                    "Use the sender email as customer_email when available."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_number": {"type": "string"},
                        "customer_email": {"type": "string"},
                        "phone_last4": {"type": "string"},
                    },
                    "required": ["order_number"],
                },
            },
            {
                "type": "function",
                "name": "search_store_knowledge",
                "description": (
                    "Search the store-owned dispensary knowledge base for hours, payments, IDs, pickup, "
                    "delivery, and policy questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "location_hint": {"type": "string"},
                    },
                    "required": ["question"],
                },
            },
        ]

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "lookup_order":
            result = self.order_provider.lookup(
                str(args.get("order_number") or "").strip(),
                customer_email=str(args.get("customer_email") or "").strip() or None,
                phone_last4=str(args.get("phone_last4") or "").strip() or None,
            )
            return result.to_tool_output()
        if name == "search_store_knowledge":
            result = self.knowledge_provider.search(
                str(args.get("question") or "").strip(),
                location_hint=str(args.get("location_hint") or "").strip() or None,
            )
            return result.to_tool_output()
        return {"status": "error", "error": f"Unknown tool: {name}"}
