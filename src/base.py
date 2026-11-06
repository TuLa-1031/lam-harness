from __future__ import annotations


from copy import deepcopy
from openai import OpenAI
import os
import logging
import json
from dotenv import load_dotenv
from typing import Any

from pathlib import Path


from env import Environment

load_dotenv()
logger = logging.getLogger(__name__)


class StepLimitError(Exception):
    """Raised when an agent exhausts its model-call budget."""

class Agent:
    def __init__(
        self,
        environment: Environment,
        model: str | None = None,
        logs_save_path: str | None = None,
        step_limit: int = 100,
        **kwargs,
    ):
        self.env = environment
        self.logs_save_path = logs_save_path
        self.step_limit = step_limit
        self.model = model or os.environ.get("MODEL")
        if not self.model:
            raise RuntimeError("MODEL is not set.")

        api_key = os.environ.get("OPEN_API_KEY")
        if not api_key:
            raise RuntimeError("OPEN_API_KEY is not set.")

        base_url = os.environ.get("OPEN_API_BASE_URL")
        if not base_url:
            raise RuntimeError("OPEN_API_BASE_URL is not set.")

        self.client = OpenAI(
            api_key = api_key,
            base_url = base_url
        )


        self.system_prompt: str = ""
        self.task_prompt: str = ""

        self.api_prompts: list[list[dict[str, Any]]] = []
        self.api_responses: list[list[dict, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.finished = False
        self.steps_taken = 0
        
        self.history: list[dict[str, Any]] = []
        
    def query_lm(
        self,
    ):
        messages = self.build_prompt()
        self.api_prompts.append(deepcopy(messages))
        step_number = self.steps_taken + 1
        print(
            f"[agent] step {step_number}/{self.steps_taken}: requesting actioin",
            flush=True,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                reasoning_effort="medium",
                max_completion_tokens=4096,
            )
        except Exception as exc:
            print(
                f"[agent] step {step_number}: model requeset failed after retires "
                f"({type(exc).__name__: {exc}})",
                flush=True,
            )
            raise
        self.api_responses.append(response.model_dump(mode="json"))
        self.steps_taken += 1
        message = self.process_response(response)

        return message

    def process_response(self, response: Any) -> dict[str, Any]:
        return response.choices[0].message.model_dump(exclude_none=True)

    def build_prompt(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system",
             "content": self.system_prompt},
            {"role": "user",
             "content": self.task_prompt},
             *self.history,
        ]
        return messages

    def run(
        self,
    ):
        try:
            while self.finished is not True:
                if self.steps_taken >= self.step_limit:
                    raise StepLimitError

                message = self.query_lm()

                self.history.append(message)

                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    observations = self.execute_tool_calls(tool_calls)
                    self.history.extend(observations)
                else: self.finished = True

        finally:
            if self.logs_save_path:
                path = Path(self.logs_save_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "prompts": self.api_prompts,
                            "responses": self.api_responses,
                        },
                        indent=2
                    )
                )



        def execute_tool_calls(
            self, tool_calls: list[dict[str, Any]]
        ) -> list[dict[str, str]]:
            raise NotImplemented
