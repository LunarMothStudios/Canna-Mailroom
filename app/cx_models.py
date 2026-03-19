from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class OrderLookupResult:
    order_number: str
    order_status: str
    fulfillment_type: str | None = None
    location_name: str | None = None
    location_id: str | None = None
    ordered_at: str | None = None
    scheduled_window: str | None = None
    ready_window: str | None = None
    payment_summary: str | None = None
    customer_safe_notes: tuple[str, ...] = ()
    source: str = ""
    verification_summary: str | None = None

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "found"
        payload["customer_safe_notes"] = list(self.customer_safe_notes)
        return payload


@dataclass(frozen=True)
class OrderNotFound:
    order_number: str
    follow_up: str
    source: str = ""

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "not_found"
        return payload


@dataclass(frozen=True)
class OrderVerificationMismatch:
    order_number: str
    follow_up: str
    verification_summary: str
    source: str = ""

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "identity_mismatch"
        return payload


OrderLookupOutcome = OrderLookupResult | OrderNotFound | OrderVerificationMismatch


@dataclass(frozen=True)
class KnowledgeAnswer:
    answer: str
    matched_topic: str
    matched_location: str | None = None
    source_ids: tuple[str, ...] = ()

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "found"
        payload["source_ids"] = list(self.source_ids)
        return payload


@dataclass(frozen=True)
class KnowledgeAmbiguous:
    follow_up: str
    options: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "ambiguous"
        payload["options"] = list(self.options)
        payload["source_ids"] = list(self.source_ids)
        return payload


@dataclass(frozen=True)
class KnowledgeNotFound:
    follow_up: str
    source_ids: tuple[str, ...] = ()

    def to_tool_output(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = "not_found"
        payload["source_ids"] = list(self.source_ids)
        return payload


KnowledgeSearchOutcome = KnowledgeAnswer | KnowledgeAmbiguous | KnowledgeNotFound


class OrderProvider(Protocol):
    def lookup(
        self,
        order_number: str,
        *,
        customer_email: str | None = None,
        phone_last4: str | None = None,
    ) -> OrderLookupOutcome:
        ...


class KnowledgeProvider(Protocol):
    def search(self, question: str, *, location_hint: str | None = None) -> KnowledgeSearchOutcome:
        ...


class AgentToolset(Protocol):
    def specs(self) -> list[dict[str, Any]]:
        ...

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        ...
