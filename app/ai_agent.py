from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.tools import GoogleWorkspaceTools


class EmailAgent:
    def __init__(
        self,
        api_key: str,
        model: str,
        tools: GoogleWorkspaceTools | None,
        system_prompt_path: str,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.tools = tools
        self.system_prompt = Path(system_prompt_path).read_text()

    def _tool_specs(self) -> list[dict[str, Any]]:
        specs = [
            {
                "type": "function",
                "name": "research_web",
                "description": "Research the public web and return a concise cited summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
        ]
        if not self.tools:
            return specs

        specs.extend(
            [
                {
                    "type": "function",
                    "name": "list_drive_files",
                    "description": "List files in Google Drive folder",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "folder_id": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                    },
                },
                {
                    "type": "function",
                    "name": "create_google_doc",
                    "description": "Create a Google Doc in a folder with optional initial content",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "initial_content": {"type": "string"},
                            "folder_id": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                },
                {
                    "type": "function",
                    "name": "append_google_doc",
                    "description": "Append content to an existing Google Doc",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["doc_id", "content"],
                    },
                },
                {
                    "type": "function",
                    "name": "read_google_doc",
                    "description": "Read text content from an existing Google Doc",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "doc_id": {"type": "string"},
                        },
                        "required": ["doc_id"],
                    },
                },
            ]
        )
        return specs

    def _research_web(self, query: str) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            input=(
                "Research the user's query and return a concise summary with source links.\n\n"
                f"Query: {query}"
            ),
        )
        return {"query": query, "summary": response.output_text.strip()}

    def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "research_web":
            return self._research_web(**args)
        if not self.tools:
            return {"error": f"Tool unavailable in this runtime: {name}"}
        if name == "list_drive_files":
            return self.tools.list_drive_files(**args)
        if name == "create_google_doc":
            return self.tools.create_google_doc(**args)
        if name == "append_google_doc":
            return self.tools.append_google_doc(**args)
        if name == "read_google_doc":
            return self.tools.read_google_doc(**args)
        return {"error": f"Unknown tool: {name}"}

    def respond_in_thread(
        self,
        user_input: str,
        thread_id: str,
        last_response_id: str | None = None,
        email_metadata: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        prefix = ""
        if email_metadata:
            prefix = (
                f"EMAIL CONTEXT\n"
                f"From: {email_metadata.get('from', '')}\n"
                f"Subject: {email_metadata.get('subject', '')}\n"
                f"Thread-ID: {thread_id}\n\n"
            )

        input_text = prefix + user_input

        response = self.client.responses.create(
            model=self.model,
            previous_response_id=last_response_id,
            input=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": input_text},
            ],
            tools=self._tool_specs(),
        )

        for _ in range(6):
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_outputs = []
            for call in function_calls:
                args = json.loads(call.arguments or "{}")
                result = self._run_tool(call.name, args)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result),
                    }
                )

            response = self.client.responses.create(
                model=self.model,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=self._tool_specs(),
            )

        final_text = response.output_text.strip()
        return final_text, response.id
