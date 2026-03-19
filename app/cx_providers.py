from __future__ import annotations

import base64
import importlib
import json
import re
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib import error, parse, request

from app.cx_models import (
    KnowledgeAmbiguous,
    KnowledgeAnswer,
    KnowledgeNotFound,
    KnowledgeProvider,
    OrderLookupResult,
    OrderNotFound,
    OrderProvider,
    OrderVerificationMismatch,
    ProviderAPIError,
    ProviderConfigurationError,
)

if TYPE_CHECKING:
    from app.settings import Settings


def _normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _tokenize(value: str | None) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "can",
        "do",
        "for",
        "how",
        "i",
        "is",
        "me",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "you",
        "your",
    }
    return {token for token in _normalize_text(value).split() if len(token) > 1 and token not in stop_words}


def _read_json_file(path: str) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        raise ProviderConfigurationError(f"Missing JSON file: {file_path}")
    try:
        return json.loads(file_path.read_text())
    except json.JSONDecodeError as err:
        raise ProviderConfigurationError(f"Invalid JSON in {file_path}: {err}") from err


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _digits_only(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _request_json_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    payload: bytes | None = None
    request_headers = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    req = request.Request(url, data=payload, headers=request_headers, method=method.upper())
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
            if not raw_body:
                return None
            return json.loads(raw_body)
    except error.HTTPError as err:
        raw_body = err.read().decode("utf-8", errors="ignore")
        message = raw_body.strip() or f"Request failed with status {err.code}"
        raise ProviderAPIError(message, status_code=err.code) from err
    except error.URLError as err:
        raise ProviderAPIError(f"Request failed: {err.reason}", status_code=503) from err


def _request_json_path(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    query: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        query_string = parse.urlencode({key: value for key, value in query.items() if value is not None})
        if query_string:
            url = f"{url}?{query_string}"
    return _request_json_url(method, url, headers=headers, body=body, timeout=timeout)


def _list_or_empty(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _coerce_money(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip() or None


def _coerce_bridge_order_outcome(payload: Any, *, source: str):
    if not isinstance(payload, dict):
        raise ProviderAPIError("Bridge order provider returned an unexpected payload.", status_code=502)

    result_status = str(payload.get("status") or "").strip().lower()
    payload_source = str(payload.get("source") or source).strip() or source
    if result_status not in {"found", "not_found", "identity_mismatch"}:
        raise ProviderAPIError("Bridge order provider must return an explicit status.", status_code=502)
    if result_status == "not_found":
        return OrderNotFound(
            order_number=str(payload.get("order_number") or "").strip(),
            follow_up=str(payload.get("follow_up") or "I couldn't find that order number."),
            source=payload_source,
        )
    if result_status == "identity_mismatch":
        return OrderVerificationMismatch(
            order_number=str(payload.get("order_number") or "").strip(),
            follow_up=str(payload.get("follow_up") or "I found the order, but I could not verify it belongs to the sender."),
            verification_summary=str(payload.get("verification_summary") or "The bridge provider could not verify the sender."),
            source=payload_source,
        )

    order_number = str(payload.get("order_number") or "").strip()
    order_status = str(payload.get("order_status") or payload.get("status_label") or "").strip()
    if not order_number or not order_status:
        raise ProviderAPIError(
            "Bridge order provider returned a found status without order_number and order_status.",
            status_code=502,
        )

    return OrderLookupResult(
        order_number=order_number,
        order_status=order_status,
        fulfillment_type=str(payload.get("fulfillment_type") or "").strip() or None,
        location_name=str(payload.get("location_name") or "").strip() or None,
        location_id=str(payload.get("location_id") or "").strip() or None,
        ordered_at=str(payload.get("ordered_at") or "").strip() or None,
        scheduled_window=str(payload.get("scheduled_window") or "").strip() or None,
        ready_window=str(payload.get("ready_window") or "").strip() or None,
        payment_summary=str(payload.get("payment_summary") or "").strip() or None,
        customer_safe_notes=_list_or_empty(payload.get("customer_safe_notes")),
        source=payload_source,
        verification_summary=str(payload.get("verification_summary") or "").strip() or None,
    )


def _pick_first_mapping(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        if isinstance(payload.get("data"), list) and payload["data"] and isinstance(payload["data"][0], dict):
            return payload["data"][0]
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    return None


def _extract_token_payload(payload: Any) -> tuple[str, int | None]:
    if not isinstance(payload, dict):
        raise ProviderAPIError("Treez auth returned an unexpected payload.", status_code=502)

    candidates = [payload]
    if isinstance(payload.get("data"), dict):
        candidates.append(payload["data"])
    if isinstance(payload.get("result"), dict):
        candidates.append(payload["result"])

    for candidate in candidates:
        for key in ("access_token", "accessToken", "token"):
            token = str(candidate.get(key) or "").strip()
            if token:
                expires_raw = candidate.get("expires_in") or candidate.get("expiresIn")
                try:
                    expires_in = int(expires_raw) if expires_raw not in {None, ""} else None
                except (TypeError, ValueError):
                    expires_in = None
                return token, expires_in

    raise ProviderAPIError("Treez auth response did not include an access token.", status_code=502)


def _topic_keywords() -> dict[str, tuple[str, ...]]:
    return {
        "hours": ("hours", "hour", "open", "close", "closing", "opening"),
        "payments": ("payment", "payments", "cash", "debit", "card", "canpay", "atm"),
        "id_requirements": ("id", "identification", "license", "passport", "medical", "patient", "card", "age", "21"),
        "pickup": ("pickup", "pick up", "curbside", "ready"),
        "delivery": ("delivery", "deliver", "delivered", "dropoff", "drop off", "minimum"),
        "refund": ("refund", "return", "exchange", "problem"),
        "cancellation": ("cancel", "cancellation", "edit", "change", "modify"),
        "contact": ("contact", "phone", "email", "call", "text", "support", "help"),
    }


class ManualKnowledgeProvider(KnowledgeProvider):
    LOCATION_SENSITIVE_TOPICS = {"hours", "payments", "pickup", "delivery", "contact"}

    def __init__(self, json_path: str):
        payload = _read_json_file(json_path)
        if not isinstance(payload, dict):
            raise ProviderConfigurationError("Store knowledge file must contain a JSON object.")

        self.path = json_path
        self.brand = payload.get("brand") if isinstance(payload.get("brand"), dict) else {}
        raw_locations = payload.get("locations")
        raw_policies = payload.get("policies")
        raw_faq_entries = payload.get("faq_entries")

        self.locations: list[dict[str, Any]] = raw_locations if isinstance(raw_locations, list) else []
        self.policies: dict[str, Any] = raw_policies if isinstance(raw_policies, dict) else {}
        self.faq_entries: list[dict[str, Any]] = raw_faq_entries if isinstance(raw_faq_entries, list) else []
        if not self.locations:
            raise ProviderConfigurationError("Store knowledge file must define at least one location.")

        self._location_index = self._build_location_index(self.locations)
        self._documents = self._build_documents()

    def _build_location_index(self, locations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for location in locations:
            location_id = str(location.get("id") or "").strip()
            if not location_id:
                raise ProviderConfigurationError("Each location in store knowledge must include a non-empty `id`.")
            index[location_id] = location
        return index

    def _brand_contact_summary(self) -> str:
        contact_bits = []
        support_phone = str(self.brand.get("support_phone") or "").strip()
        support_email = str(self.brand.get("support_email") or "").strip()
        support_url = str(self.brand.get("support_url") or "").strip()
        if support_phone:
            contact_bits.append(f"call {support_phone}")
        if support_email:
            contact_bits.append(f"email {support_email}")
        if support_url:
            contact_bits.append(f"visit {support_url}")
        if not contact_bits:
            return "contact the store directly"
        return " or ".join(contact_bits)

    def _format_hours(self, hours: Any) -> str:
        if isinstance(hours, str) and hours.strip():
            return hours.strip()
        if not isinstance(hours, dict):
            return "Hours are not listed in the store knowledge file."
        ordered_days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        if isinstance(hours.get("daily"), str) and hours.get("daily", "").strip():
            return f"Daily: {hours['daily'].strip()}"
        entries = [f"{day.capitalize()}: {str(hours.get(day)).strip()}" for day in ordered_days if str(hours.get(day) or "").strip()]
        return "; ".join(entries) if entries else "Hours are not listed in the store knowledge file."

    def _match_locations(self, haystack: str) -> list[dict[str, Any]]:
        normalized_haystack = _normalize_text(haystack)
        matches: list[dict[str, Any]] = []
        for location in self.locations:
            name = str(location.get("name") or "").strip()
            aliases = location.get("aliases") if isinstance(location.get("aliases"), list) else []
            candidates = [name, str(location.get("id") or "")] + [str(alias) for alias in aliases]
            for candidate in candidates:
                normalized_candidate = _normalize_text(candidate)
                if normalized_candidate and normalized_candidate in normalized_haystack:
                    matches.append(location)
                    break
        return matches

    def _build_documents(self) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        topic_keywords = _topic_keywords()

        for faq in self.faq_entries:
            answer = str(faq.get("answer") or "").strip()
            if not answer:
                continue
            location_ids = faq.get("location_ids") if isinstance(faq.get("location_ids"), list) else []
            keywords = {str(item) for item in faq.get("keywords", []) if str(item).strip()}
            documents.append(
                {
                    "id": str(faq.get("id") or f"faq-{len(documents) + 1}"),
                    "topic": str(faq.get("topic") or "faq"),
                    "location_ids": tuple(str(item) for item in location_ids if str(item).strip()),
                    "answer": answer,
                    "keywords": keywords,
                    "tokens": _tokenize(f"{faq.get('question', '')} {answer} {' '.join(keywords)}"),
                    "location_name": None,
                }
            )

        for policy_name, policy_text in self.policies.items():
            text = str(policy_text or "").strip()
            if not text:
                continue
            documents.append(
                {
                    "id": f"policy:{policy_name}",
                    "topic": policy_name,
                    "location_ids": (),
                    "answer": text,
                    "keywords": set(topic_keywords.get(policy_name, (policy_name,))),
                    "tokens": _tokenize(text),
                    "location_name": None,
                }
            )

        documents.append(
            {
                "id": "brand:contact",
                "topic": "contact",
                "location_ids": (),
                "answer": f"For direct help, {self._brand_contact_summary()}.",
                "keywords": set(topic_keywords["contact"]),
                "tokens": _tokenize(self._brand_contact_summary()),
                "location_name": None,
            }
        )

        for location in self.locations:
            location_id = str(location["id"])
            location_name = str(location.get("name") or location_id)
            location_tokens = _tokenize(f"{location_id} {location_name} {' '.join(str(alias) for alias in location.get('aliases', []))}")

            documents.append(
                {
                    "id": f"location:{location_id}:hours",
                    "topic": "hours",
                    "location_ids": (location_id,),
                    "answer": f"{location_name} hours: {self._format_hours(location.get('hours'))}",
                    "keywords": set(_topic_keywords()["hours"]),
                    "tokens": location_tokens | _tokenize(self._format_hours(location.get("hours"))),
                    "location_name": location_name,
                }
            )

            payment_methods = [str(item).strip() for item in location.get("payment_methods", []) if str(item).strip()]
            if payment_methods:
                documents.append(
                    {
                        "id": f"location:{location_id}:payments",
                        "topic": "payments",
                        "location_ids": (location_id,),
                        "answer": f"{location_name} currently lists these payment methods: {', '.join(payment_methods)}.",
                        "keywords": set(_topic_keywords()["payments"]),
                        "tokens": location_tokens | _tokenize(" ".join(payment_methods)),
                        "location_name": location_name,
                    }
                )

            access_bits: list[str] = []
            if location.get("supports_adult_use") is True:
                access_bits.append("Adult-use customers are welcome.")
            if location.get("supports_medical") is True:
                access_bits.append("Medical patients are welcome.")
            id_requirements = [str(item).strip() for item in location.get("id_requirements", []) if str(item).strip()]
            if id_requirements:
                access_bits.extend(id_requirements)
            if access_bits:
                documents.append(
                    {
                        "id": f"location:{location_id}:id_requirements",
                        "topic": "id_requirements",
                        "location_ids": (location_id,),
                        "answer": f"{location_name}: {' '.join(access_bits)}",
                        "keywords": set(_topic_keywords()["id_requirements"]),
                        "tokens": location_tokens | _tokenize(" ".join(access_bits)),
                        "location_name": location_name,
                    }
                )

            pickup_notes = str(location.get("pickup_notes") or "").strip()
            if pickup_notes:
                documents.append(
                    {
                        "id": f"location:{location_id}:pickup",
                        "topic": "pickup",
                        "location_ids": (location_id,),
                        "answer": f"{location_name} pickup: {pickup_notes}",
                        "keywords": set(_topic_keywords()["pickup"]),
                        "tokens": location_tokens | _tokenize(pickup_notes),
                        "location_name": location_name,
                    }
                )

            delivery_notes = str(location.get("delivery_notes") or "").strip()
            if delivery_notes:
                documents.append(
                    {
                        "id": f"location:{location_id}:delivery",
                        "topic": "delivery",
                        "location_ids": (location_id,),
                        "answer": f"{location_name} delivery: {delivery_notes}",
                        "keywords": set(_topic_keywords()["delivery"]),
                        "tokens": location_tokens | _tokenize(delivery_notes),
                        "location_name": location_name,
                    }
                )

            contact_email = str(location.get("contact_email") or "").strip()
            contact_phone = str(location.get("contact_phone") or "").strip()
            contact_parts = []
            if contact_phone:
                contact_parts.append(f"call {contact_phone}")
            if contact_email:
                contact_parts.append(f"email {contact_email}")
            if contact_parts:
                documents.append(
                    {
                        "id": f"location:{location_id}:contact",
                        "topic": "contact",
                        "location_ids": (location_id,),
                        "answer": f"For {location_name}, {' or '.join(contact_parts)}.",
                        "keywords": set(_topic_keywords()["contact"]),
                        "tokens": location_tokens | _tokenize(" ".join(contact_parts)),
                        "location_name": location_name,
                    }
                )

        return documents

    def _match_topics(self, question: str) -> set[str]:
        normalized_question = _normalize_text(question)
        question_tokens = _tokenize(question)
        matches: set[str] = set()
        for topic, keywords in _topic_keywords().items():
            for keyword in keywords:
                normalized_keyword = _normalize_text(keyword)
                if not normalized_keyword:
                    continue
                if " " in normalized_keyword and normalized_keyword in normalized_question:
                    matches.add(topic)
                    break
                if normalized_keyword in question_tokens:
                    matches.add(topic)
                    break
        return matches

    def _score_document(
        self,
        document: dict[str, Any],
        *,
        normalized_question: str,
        question_tokens: set[str],
        matched_location_ids: set[str],
        matched_topics: set[str],
    ) -> int:
        score = 0
        if document["topic"] in matched_topics:
            score += 6
        keyword_hits = 0
        for keyword in document["keywords"]:
            normalized_keyword = _normalize_text(keyword)
            if not normalized_keyword:
                continue
            if " " in normalized_keyword:
                if normalized_keyword in normalized_question:
                    keyword_hits += 2
            elif normalized_keyword in question_tokens:
                keyword_hits += 1
        score += keyword_hits * 3
        score += len(question_tokens & set(document["tokens"]))
        if document["location_ids"] and matched_location_ids.intersection(document["location_ids"]):
            score += 6
        return score

    def search(self, question: str, *, location_hint: str | None = None):
        cleaned_question = question.strip()
        if not cleaned_question:
            return KnowledgeNotFound("What store question can I help with?")

        search_space = " ".join(item for item in [cleaned_question, location_hint or ""] if item.strip())
        matched_locations = self._match_locations(search_space)
        matched_location_ids = {str(location["id"]) for location in matched_locations}
        matched_topics = self._match_topics(cleaned_question)

        if len(matched_locations) > 1:
            return KnowledgeAmbiguous(
                follow_up="Which store location do you mean?",
                options=tuple(str(location.get("name") or location["id"]) for location in matched_locations),
            )

        if not matched_locations and len(self.locations) > 1 and matched_topics.intersection(self.LOCATION_SENSITIVE_TOPICS):
            return KnowledgeAmbiguous(
                follow_up="Which store location are you asking about?",
                options=tuple(str(location.get("name") or location["id"]) for location in self.locations),
            )

        allowed_location_ids = matched_location_ids
        if not allowed_location_ids and len(self.locations) == 1:
            allowed_location_ids = {str(self.locations[0]["id"])}

        normalized_question = _normalize_text(cleaned_question)
        question_tokens = _tokenize(cleaned_question)
        candidates: list[tuple[int, dict[str, Any]]] = []

        for document in self._documents:
            doc_location_ids = set(document["location_ids"])
            if doc_location_ids and allowed_location_ids and not doc_location_ids.intersection(allowed_location_ids):
                continue
            if doc_location_ids and not allowed_location_ids and len(self.locations) > 1:
                continue
            score = self._score_document(
                document,
                normalized_question=normalized_question,
                question_tokens=question_tokens,
                matched_location_ids=matched_location_ids,
                matched_topics=matched_topics,
            )
            if score > 0:
                candidates.append((score, document))

        if not candidates:
            return KnowledgeNotFound(
                f"I couldn't find that in the store knowledge base. For direct help, contact the store: {self._brand_contact_summary()}."
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_document = candidates[0]
        tied_documents = [document for score, document in candidates if score == best_score]
        tied_locations = {
            document["location_name"]
            for document in tied_documents
            if document["location_name"] and document["topic"] == best_document["topic"]
        }
        if len(tied_locations) > 1:
            return KnowledgeAmbiguous(
                follow_up="I found more than one matching store location. Which one do you mean?",
                options=tuple(sorted(tied_locations)),
                source_ids=tuple(document["id"] for document in tied_documents),
            )

        return KnowledgeAnswer(
            answer=str(best_document["answer"]),
            matched_topic=str(best_document["topic"]),
            matched_location=best_document["location_name"],
            source_ids=(str(best_document["id"]),),
        )


class ManualOrderProvider(OrderProvider):
    def __init__(self, json_path: str):
        payload = _read_json_file(json_path)
        if not isinstance(payload, dict) or not isinstance(payload.get("orders"), list):
            raise ProviderConfigurationError("Manual order file must contain an object with an `orders` array.")
        self.path = json_path
        self.orders = {
            str(order.get("order_number") or "").strip(): order
            for order in payload["orders"]
            if isinstance(order, dict) and str(order.get("order_number") or "").strip()
        }

    def lookup(
        self,
        order_number: str,
        *,
        customer_email: str | None = None,
        phone_last4: str | None = None,
    ):
        clean_order_number = order_number.strip()
        if not clean_order_number:
            return OrderNotFound(order_number="", follow_up="Please share the order number you want me to check.", source="manual")

        order = self.orders.get(clean_order_number)
        if not order:
            return OrderNotFound(
                order_number=clean_order_number,
                follow_up="I couldn't find that order number in the configured manual order file.",
                source="manual",
            )

        expected_email = str(order.get("customer_email") or "").strip().lower()
        if customer_email and expected_email and customer_email.strip().lower() != expected_email:
            return OrderVerificationMismatch(
                order_number=clean_order_number,
                follow_up="I found the order number, but the sender email does not match the configured customer email.",
                verification_summary="Sender email did not match the stored customer email.",
                source="manual",
            )

        expected_last4 = str(order.get("phone_last4") or "").strip()
        if phone_last4 and expected_last4 and phone_last4.strip() != expected_last4:
            return OrderVerificationMismatch(
                order_number=clean_order_number,
                follow_up="I found the order number, but the phone digits provided do not match the configured order record.",
                verification_summary="Phone last four digits did not match the stored order record.",
                source="manual",
            )

        notes = tuple(str(item).strip() for item in order.get("notes", []) if str(item).strip())
        return OrderLookupResult(
            order_number=clean_order_number,
            order_status=str(order.get("status") or "Unknown"),
            fulfillment_type=str(order.get("fulfillment_type") or "").strip() or None,
            location_name=str(order.get("location_name") or "").strip() or None,
            location_id=str(order.get("location_id") or "").strip() or None,
            ordered_at=str(order.get("ordered_at") or "").strip() or None,
            scheduled_window=str(order.get("scheduled_window") or "").strip() or None,
            ready_window=str(order.get("ready_window") or "").strip() or None,
            payment_summary=str(order.get("payment_summary") or "").strip() or None,
            customer_safe_notes=notes,
            source="manual",
            verification_summary="Matched against the configured manual order file.",
        )


class DutchieOrderProvider(OrderProvider):
    def __init__(self, location_key: str, integrator_key: str = "", base_url: str = "https://api.pos.dutchie.com"):
        self.location_key = location_key.strip()
        self.integrator_key = integrator_key.strip()
        self.base_url = base_url.rstrip("/")
        if not self.location_key:
            raise ProviderConfigurationError("DUTCHIE_LOCATION_KEY is required when ORDER_PROVIDER=dutchie.")
        self._location_identity: dict[str, Any] | None = None

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.location_key}:{self.integrator_key}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        return _request_json_path(
            self.base_url,
            path,
            method=method,
            query=query,
            headers={
                "Accept": "application/json",
                "Authorization": self._auth_header(),
            },
            body=body,
        )

    def _get_location_identity(self) -> dict[str, Any]:
        if self._location_identity is None:
            payload = self._request_json("GET", "/whoami")
            if not isinstance(payload, dict):
                raise ProviderAPIError("Dutchie /whoami returned an unexpected payload.", status_code=502)
            self._location_identity = payload
        return self._location_identity

    def _verify_customer(
        self,
        *,
        customer_email: str | None,
        order_customer_id: Any,
        phone_last4: str | None,
    ) -> tuple[str, str | None]:
        if not customer_email and not phone_last4:
            return "not_requested", None

        verification_notes: list[str] = []
        verified = False
        if customer_email:
            try:
                payload = self._request_json(
                    "POST",
                    "/customer/customerLookup",
                    body={"EmailAddress": customer_email},
                )
            except ProviderAPIError as err:
                if err.status_code == 404:
                    return "unverified", "The sender email could not be matched to a Dutchie customer record."
                if err.status_code == 403:
                    return "unverified", "Dutchie customer verification is not available with the current permission scopes."
                else:
                    raise
            else:
                if not isinstance(payload, dict):
                    raise ProviderAPIError("Dutchie customer lookup returned an unexpected payload.", status_code=502)
                customer_id = payload.get("customerId")
                if not customer_id:
                    return "unverified", "Dutchie customer verification did not return a customer record for the sender email."
                if not order_customer_id:
                    return "unverified", "Dutchie preorder status did not expose a customer id for sender verification."
                if str(customer_id) != str(order_customer_id):
                    return "mismatch", "The sender email matched a different Dutchie customer than the order record."
                verified = True
                verification_notes.append("Matched the sender email to the Dutchie customer record.")

        if phone_last4:
            if verified:
                verification_notes.append("Dutchie order status does not expose enough data to verify phone last four digits.")
            else:
                return "unverified", "Dutchie order status does not expose enough data to verify the provided phone last four digits."

        if verified:
            return "matched", " ".join(verification_notes) if verification_notes else None
        return "unverified", "Dutchie could not verify the sender against the order."

    def lookup(
        self,
        order_number: str,
        *,
        customer_email: str | None = None,
        phone_last4: str | None = None,
    ):
        clean_order_number = order_number.strip()
        if not clean_order_number:
            return OrderNotFound(order_number="", follow_up="Please share the order number you want me to check.", source="dutchie")

        payload = self._request_json("GET", "/preorder/Status", query={"PreOrderId": clean_order_number})
        if not isinstance(payload, list) or not payload:
            return OrderNotFound(
                order_number=clean_order_number,
                follow_up="I couldn't find that order number in Dutchie.",
                source="dutchie",
            )

        order = payload[0]
        if not isinstance(order, dict):
            raise ProviderAPIError("Dutchie preorder status returned an unexpected payload.", status_code=502)

        verification_status, verification_summary = self._verify_customer(
            customer_email=customer_email,
            order_customer_id=order.get("customerId"),
            phone_last4=phone_last4,
        )
        if verification_status in {"mismatch", "unverified"}:
            return OrderVerificationMismatch(
                order_number=clean_order_number,
                follow_up="I found the order number, but I could not verify it belongs to the sender.",
                verification_summary=verification_summary or "Dutchie could not verify the sender against the order.",
                source="dutchie",
            )

        location = self._get_location_identity()
        total = order.get("total")
        payment_summary = None
        if total not in {None, ""}:
            try:
                payment_summary = (
                    f"Estimated total: ${float(total):.2f}. "
                    "Dutchie's status endpoint does not include payment-state details."
                )
            except (TypeError, ValueError):
                payment_summary = "Dutchie's status endpoint returned an estimated total, but it was not formatted as a currency value."

        notes: list[str] = []
        rejected_reason = str(order.get("rejectedReason") or "").strip()
        if rejected_reason:
            notes.append(f"Provider note: {rejected_reason}")
        if order.get("isUpdateable") is True or order.get("isCancellable") is True:
            notes.append("This order may still be updateable or cancellable in Dutchie, but this email agent cannot change orders.")
        if verification_status == "matched" and verification_summary:
            notes.append(verification_summary)

        return OrderLookupResult(
            order_number=str(order.get("preOrderId") or clean_order_number),
            order_status=str(order.get("status") or "Unknown"),
            fulfillment_type=str(order.get("orderType") or "").strip() or None,
            location_name=str(location.get("locationName") or "").strip() or None,
            location_id=str(location.get("locationId") or "").strip() or None,
            ordered_at=str(order.get("orderDate") or "").strip() or None,
            payment_summary=payment_summary,
            customer_safe_notes=tuple(notes),
            source="dutchie",
            verification_summary=verification_summary,
        )


class BridgeOrderProvider(OrderProvider):
    def __init__(
        self,
        endpoint_url: str,
        *,
        auth_token: str = "",
        source: str = "bridge",
        timeout_seconds: int = 15,
        provider_name: str | None = None,
    ):
        self.endpoint_url = endpoint_url.strip()
        self.auth_token = auth_token.strip()
        self.source = source.strip() or "bridge"
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.provider_name = (provider_name or self.source).strip() or self.source
        if not self.endpoint_url:
            raise ProviderConfigurationError("Bridge order provider requires a non-empty endpoint URL.")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def lookup(
        self,
        order_number: str,
        *,
        customer_email: str | None = None,
        phone_last4: str | None = None,
    ):
        clean_order_number = order_number.strip()
        if not clean_order_number:
            return OrderNotFound(order_number="", follow_up="Please share the order number you want me to check.", source=self.source)

        body = {
            "provider": self.provider_name,
            "order_number": clean_order_number,
            "customer_email": customer_email,
            "phone_last4": phone_last4,
        }
        try:
            payload = _request_json_url(
                "POST",
                self.endpoint_url,
                headers=self._headers(),
                body=body,
                timeout=self.timeout_seconds,
            )
        except ProviderAPIError as err:
            if err.status_code == 404:
                return OrderNotFound(
                    order_number=clean_order_number,
                    follow_up=f"I couldn't find that order number in {self.provider_name}.",
                    source=self.source,
                )
            raise
        return _coerce_bridge_order_outcome(payload, source=self.source)


class JaneOrderProvider(BridgeOrderProvider):
    def __init__(self, bridge_url: str, bridge_token: str = "", timeout_seconds: int = 15):
        if not bridge_url.strip():
            raise ProviderConfigurationError("JANE_BRIDGE_URL is required when ORDER_PROVIDER=jane.")
        super().__init__(
            bridge_url,
            auth_token=bridge_token,
            source="jane",
            timeout_seconds=timeout_seconds,
            provider_name="jane",
        )


class TreezOrderProvider(OrderProvider):
    def __init__(
        self,
        dispensary: str,
        client_id: str,
        api_key: str,
        base_url: str = "https://api.treez.io",
    ):
        self.dispensary = dispensary.strip()
        self.client_id = client_id.strip()
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        if not self.dispensary:
            raise ProviderConfigurationError("TREEZ_DISPENSARY is required when ORDER_PROVIDER=treez.")
        if not self.client_id:
            raise ProviderConfigurationError("TREEZ_CLIENT_ID is required when ORDER_PROVIDER=treez.")
        if not self.api_key:
            raise ProviderConfigurationError("TREEZ_API_KEY is required when ORDER_PROVIDER=treez.")
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    def _auth_request_body(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "api_key": self.api_key,
        }

    def _fetch_access_token(self) -> tuple[str, int | None]:
        payload = _request_json_path(
            self.base_url,
            "/auth/v1/config/api/gettokens",
            method="POST",
            headers={"Accept": "application/json"},
            body=self._auth_request_body(),
        )
        return _extract_token_payload(payload)

    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        if not force_refresh and self._access_token and now < self._access_token_expires_at:
            return self._access_token

        token, expires_in = self._fetch_access_token()
        ttl_seconds = expires_in if expires_in and expires_in > 0 else 7200
        self._access_token = token
        self._access_token_expires_at = now + max(1, ttl_seconds - 60)
        return token

    def _request_ticket(self, path: str) -> Any:
        last_error: ProviderAPIError | None = None
        for attempt in range(2):
            token = self._get_access_token(force_refresh=attempt > 0)
            try:
                return _request_json_path(
                    self.base_url,
                    path,
                    method="GET",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
            except ProviderAPIError as err:
                last_error = err
                if err.status_code == 401 and attempt == 0:
                    self._access_token = None
                    self._access_token_expires_at = 0.0
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise ProviderAPIError("Treez ticket request failed before any response was returned.", status_code=503)

    def _verify_customer(
        self,
        ticket: dict[str, Any],
        *,
        customer_email: str | None,
        phone_last4: str | None,
    ) -> tuple[str, str | None]:
        if not customer_email and not phone_last4:
            return "not_requested", None

        notes: list[str] = []
        verified = False
        customer_payload = ticket.get("customer") if isinstance(ticket.get("customer"), dict) else {}
        order_email = _normalize_email(
            ticket.get("customer_email")
            or ticket.get("email")
            or customer_payload.get("email")
        )
        if customer_email:
            expected_email = _normalize_email(customer_email)
            if not order_email:
                return "unverified", "Treez lookup did not expose a stable email field for sender verification."
            if expected_email != order_email:
                return "mismatch", "The sender email did not match the email on the Treez ticket."
            verified = True
            notes.append("Matched the sender email to the Treez ticket.")

        order_phone_last4 = _digits_only(
            ticket.get("phone_last4")
            or ticket.get("phone")
            or customer_payload.get("phone")
        )[-4:]
        if phone_last4:
            expected_last4 = _digits_only(phone_last4)[-4:]
            if order_phone_last4 and expected_last4 and expected_last4 != order_phone_last4:
                return "mismatch", "The phone digits provided did not match the Treez ticket."
            if order_phone_last4 and expected_last4:
                verified = True
                notes.append("Matched the phone digits to the Treez ticket.")
            else:
                if verified:
                    notes.append("Treez lookup did not expose enough phone data to verify the last four digits.")
                else:
                    return "unverified", "Treez lookup did not expose enough phone data to verify the provided last four digits."

        if verified:
            return "matched", " ".join(notes) if notes else None
        return "unverified", "Treez could not verify the sender against the order."

    def lookup(
        self,
        order_number: str,
        *,
        customer_email: str | None = None,
        phone_last4: str | None = None,
    ):
        clean_order_number = order_number.strip()
        if not clean_order_number:
            return OrderNotFound(order_number="", follow_up="Please share the order number you want me to check.", source="treez")

        try:
            payload = self._request_ticket(f"/v2.0/dispensary/{parse.quote(self.dispensary)}/ticket/ordernumber/{parse.quote(clean_order_number)}")
        except ProviderAPIError as err:
            if err.status_code == 404:
                return OrderNotFound(
                    order_number=clean_order_number,
                    follow_up="I couldn't find that order number in Treez.",
                    source="treez",
                )
            raise

        if isinstance(payload, dict) and str(payload.get("resultCode") or "").strip().upper() in {"NOT_FOUND", "NO_RECORDS"}:
            return OrderNotFound(
                order_number=clean_order_number,
                follow_up="I couldn't find that order number in Treez.",
                source="treez",
            )

        ticket = _pick_first_mapping(payload)
        if not ticket:
            return OrderNotFound(
                order_number=clean_order_number,
                follow_up="I couldn't find that order number in Treez.",
                source="treez",
            )

        verification_status, verification_summary = self._verify_customer(
            ticket,
            customer_email=customer_email,
            phone_last4=phone_last4,
        )
        if verification_status in {"mismatch", "unverified"}:
            return OrderVerificationMismatch(
                order_number=clean_order_number,
                follow_up="I found the order number, but I could not verify it belongs to the sender.",
                verification_summary=verification_summary or "Treez could not verify the sender against the order.",
                source="treez",
            )

        total = _coerce_money(
            ticket.get("total")
            or ticket.get("grand_total")
            or ticket.get("order_total")
        )
        payment_status = str(ticket.get("payment_status") or ticket.get("paymentStatus") or "").strip()
        payment_summary_parts = [part for part in [payment_status, total] if part]
        notes: list[str] = []
        for candidate in (
            ticket.get("ticket_note"),
            ticket.get("notes"),
            ticket.get("refund_reason"),
            ticket.get("status_message"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                notes.append(candidate.strip())
        if verification_status == "matched" and verification_summary:
            notes.append(verification_summary)

        return OrderLookupResult(
            order_number=str(ticket.get("order_number") or ticket.get("orderNumber") or clean_order_number),
            order_status=str(ticket.get("order_status") or ticket.get("status") or "Unknown"),
            fulfillment_type=str(ticket.get("type") or ticket.get("fulfillment_type") or "").strip() or None,
            location_name=str(ticket.get("location_name") or ticket.get("locationName") or self.dispensary).strip() or None,
            location_id=str(ticket.get("location_id") or ticket.get("locationId") or "").strip() or None,
            ordered_at=str(ticket.get("date_created") or ticket.get("created_at") or ticket.get("createdAt") or "").strip() or None,
            scheduled_window=str(ticket.get("scheduled_date") or ticket.get("scheduled_window") or "").strip() or None,
            ready_window=str(ticket.get("ready_window") or ticket.get("ready_at") or ticket.get("packed_ready_at") or "").strip() or None,
            payment_summary=". ".join(payment_summary_parts) if payment_summary_parts else None,
            customer_safe_notes=tuple(notes),
            source="treez",
            verification_summary=verification_summary,
        )


def _import_object(import_path: str) -> Any:
    module_name = ""
    attr_name = ""
    if ":" in import_path:
        module_name, attr_name = import_path.split(":", 1)
    elif "." in import_path:
        module_name, attr_name = import_path.rsplit(".", 1)
    else:
        raise ProviderConfigurationError(
            "ORDER_PROVIDER_FACTORY must use `module:attribute` or `module.attribute` syntax."
        )
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr_name)
    except AttributeError as err:
        raise ProviderConfigurationError(f"Factory `{attr_name}` was not found in module `{module_name}`.") from err


def _build_custom_order_provider(import_path: str, settings: Settings) -> OrderProvider:
    if not import_path.strip():
        raise ProviderConfigurationError("ORDER_PROVIDER_FACTORY is required when ORDER_PROVIDER=custom.")
    factory = _import_object(import_path.strip())
    if callable(factory):
        try:
            provider = factory(settings)
        except TypeError:
            provider = factory()
    else:
        provider = factory
    if not hasattr(provider, "lookup"):
        raise ProviderConfigurationError("Custom order provider must expose a `lookup(...)` method.")
    return provider


def load_order_provider(settings: Settings) -> OrderProvider:
    if settings.order_provider == "manual":
        return ManualOrderProvider(settings.manual_order_file)
    if settings.order_provider == "dutchie":
        return DutchieOrderProvider(
            location_key=settings.dutchie_location_key,
            integrator_key=settings.dutchie_integrator_key,
            base_url=settings.dutchie_api_base_url,
        )
    if settings.order_provider == "treez":
        return TreezOrderProvider(
            dispensary=settings.treez_dispensary,
            client_id=settings.treez_client_id,
            api_key=settings.treez_api_key,
            base_url=settings.treez_api_base_url,
        )
    if settings.order_provider == "jane":
        return JaneOrderProvider(
            bridge_url=settings.jane_bridge_url,
            bridge_token=settings.jane_bridge_token,
            timeout_seconds=settings.jane_bridge_timeout_seconds,
        )
    if settings.order_provider == "bridge":
        return BridgeOrderProvider(
            settings.bridge_order_provider_url,
            auth_token=settings.bridge_order_provider_token,
            source=settings.bridge_order_provider_source,
            timeout_seconds=settings.bridge_order_provider_timeout_seconds,
        )
    if settings.order_provider == "custom":
        return _build_custom_order_provider(settings.order_provider_factory, settings)
    raise ProviderConfigurationError(f"Unsupported ORDER_PROVIDER: {settings.order_provider}")


def load_knowledge_provider(settings: Settings) -> KnowledgeProvider:
    if settings.knowledge_provider != "manual":
        raise ProviderConfigurationError(f"Unsupported KNOWLEDGE_PROVIDER: {settings.knowledge_provider}")
    return ManualKnowledgeProvider(settings.store_knowledge_file)
