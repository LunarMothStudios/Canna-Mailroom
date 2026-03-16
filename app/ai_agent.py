from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.cx_models import AgentToolset


class EmailAgent:
    def __init__(
        self,
        api_key: str,
        model: str,
        toolset: AgentToolset,
        system_prompt_path: str,
        client: Any | None = None,
    ):
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
        self.client = client
        self.model = model
        self.toolset = toolset
        self.system_prompt = Path(system_prompt_path).read_text()

    def _tool_specs(self) -> list[dict[str, Any]]:
        return self.toolset.specs()

    def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.toolset.run(name, args)

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
