from __future__ import annotations

import email.utils
import json
from pathlib import Path
from typing import Any

from app.cx_models import AgentToolset


class EmailAgent:
    MAX_TOOL_ROUNDS = 6
    TOOL_FALLBACK_MESSAGE = (
        "I hit an internal issue while checking that. Please resend your question or order number, "
        "and contact the store directly if you need urgent help."
    )

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

    def _trusted_sender_email(self, email_metadata: dict[str, str] | None) -> str | None:
        if not email_metadata:
            return None
        from_header = str(email_metadata.get("from") or "").strip()
        parsed_email = email.utils.parseaddr(from_header)[1].strip().lower()
        if parsed_email:
            return parsed_email
        return None

    def _prepare_tool_args(
        self,
        *,
        tool_name: str,
        raw_arguments: str | None,
        trusted_sender_email: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            parsed_arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return None, {
                "status": "error",
                "error": "The tool arguments were invalid JSON.",
            }

        if not isinstance(parsed_arguments, dict):
            return None, {
                "status": "error",
                "error": "The tool arguments must be a JSON object.",
            }

        if tool_name == "lookup_order" and trusted_sender_email:
            parsed_arguments["customer_email"] = trusted_sender_email
        return parsed_arguments, None

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
        trusted_sender_email = self._trusted_sender_email(email_metadata)

        response = self.client.responses.create(
            model=self.model,
            previous_response_id=last_response_id,
            input=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": input_text},
            ],
            tools=self._tool_specs(),
        )

        for _ in range(self.MAX_TOOL_ROUNDS):
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            tool_outputs = []
            for call in function_calls:
                args, argument_error = self._prepare_tool_args(
                    tool_name=call.name,
                    raw_arguments=call.arguments,
                    trusted_sender_email=trusted_sender_email,
                )
                result = argument_error if argument_error is not None else self._run_tool(call.name, args or {})
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

        remaining_function_calls = [item for item in response.output if item.type == "function_call"]
        final_text = response.output_text.strip()
        if remaining_function_calls or not final_text:
            return self.TOOL_FALLBACK_MESSAGE, response.id
        return final_text, response.id
