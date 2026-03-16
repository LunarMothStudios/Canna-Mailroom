from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.ai_agent import EmailAgent


class FakeResponse:
    def __init__(self, response_id: str, output_text: str, output: list[object] | None = None):
        self.id = response_id
        self.output_text = output_text
        self.output = output or []


class FakeResponsesAPI:
    def __init__(self, queued_responses: list[FakeResponse]):
        self.queued_responses = list(queued_responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queued_responses:
            raise AssertionError("No fake responses left.")
        return self.queued_responses.pop(0)


class FakeClient:
    def __init__(self, queued_responses: list[FakeResponse]):
        self.responses = FakeResponsesAPI(queued_responses)


class RecordingToolset:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def specs(self):
        return [
            {"type": "function", "name": "lookup_order", "parameters": {"type": "object", "properties": {}}},
            {"type": "function", "name": "search_store_knowledge", "parameters": {"type": "object", "properties": {}}},
        ]

    def run(self, name: str, args: dict):
        self.calls.append((name, args))
        return {"status": "found", "name": name}


class EmailAgentTests(unittest.TestCase):
    def make_prompt_file(self) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "prompt.md"
        path.write_text("Test prompt")
        return str(path)

    def test_lookup_order_function_call_is_executed(self):
        toolset = RecordingToolset()
        fake_client = FakeClient(
            [
                FakeResponse(
                    "resp-1",
                    "",
                    [
                        SimpleNamespace(
                            type="function_call",
                            name="lookup_order",
                            arguments=json.dumps({"order_number": "100100", "customer_email": "alex@example.com"}),
                            call_id="call-1",
                        )
                    ],
                ),
                FakeResponse("resp-2", "Your order is ready."),
            ]
        )
        agent = EmailAgent(
            api_key="test",
            model="gpt-5.4",
            toolset=toolset,
            system_prompt_path=self.make_prompt_file(),
            client=fake_client,
        )

        reply, response_id = agent.respond_in_thread("Where is order 100100?", thread_id="thread-1")

        self.assertEqual(reply, "Your order is ready.")
        self.assertEqual(response_id, "resp-2")
        self.assertEqual(toolset.calls[0][0], "lookup_order")

    def test_search_store_knowledge_function_call_is_executed(self):
        toolset = RecordingToolset()
        fake_client = FakeClient(
            [
                FakeResponse(
                    "resp-1",
                    "",
                    [
                        SimpleNamespace(
                            type="function_call",
                            name="search_store_knowledge",
                            arguments=json.dumps({"question": "What are your hours?", "location_hint": "Downtown"}),
                            call_id="call-1",
                        )
                    ],
                ),
                FakeResponse("resp-2", "Downtown is open until 9 PM."),
            ]
        )
        agent = EmailAgent(
            api_key="test",
            model="gpt-5.4",
            toolset=toolset,
            system_prompt_path=self.make_prompt_file(),
            client=fake_client,
        )

        reply, _ = agent.respond_in_thread("What are your hours?", thread_id="thread-1")

        self.assertEqual(reply, "Downtown is open until 9 PM.")
        self.assertEqual(toolset.calls[0][0], "search_store_knowledge")

    def test_follow_up_can_be_returned_without_any_tool_call(self):
        toolset = RecordingToolset()
        fake_client = FakeClient([FakeResponse("resp-1", "What is the order number?")])
        agent = EmailAgent(
            api_key="test",
            model="gpt-5.4",
            toolset=toolset,
            system_prompt_path=self.make_prompt_file(),
            client=fake_client,
        )

        reply, _ = agent.respond_in_thread("Can you check my order?", thread_id="thread-1")

        self.assertEqual(reply, "What is the order number?")
        self.assertEqual(toolset.calls, [])

    def test_tool_surface_is_exactly_the_two_cx_tools(self):
        toolset = RecordingToolset()
        agent = EmailAgent(
            api_key="test",
            model="gpt-5.4",
            toolset=toolset,
            system_prompt_path=self.make_prompt_file(),
            client=FakeClient([FakeResponse("resp-1", "ok")]),
        )

        tool_names = [item["name"] for item in agent._tool_specs()]

        self.assertEqual(tool_names, ["lookup_order", "search_store_knowledge"])
        self.assertNotIn("research_web", tool_names)
