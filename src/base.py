from openai import OpenAI
import re
import os
import subprocess
from dotenv import load_dotenv
from typing import Any

load_dotenv()


class StepLimitError(Exception):
    """Raised when an agent exhausts its model-call budget."""

class Agent:
    def __init__(
        self,
        **kwargs,
    ):
        self.messages: list[dict] = []
        self.client = OpenAI(
            api_key=os.getenv("OPEN_API_KEY"),
            base_url = os.getenv("OPEN_API_BASE_URL")
        )
        self.model = os.getenv("model")
        self.history: list[dict[str, Any]] = []
        
    def query_lm(
        self,
        messages: list[dict[str, Any]]
    ):
        responses = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        return responses.choices[0].message.content

    def parse_action(
        self,
        lm_output: str
    ) -> str:
        matches = re.findall(
            r"```bash-action\s*\n(.*?)\n```",
            lm_output,
            re.DOTALL
        )
        return matches[0].strip() if matches else ""

    def execute_action(
        command: str,
        ) -> str:
        results = subprocess.run(
            command,
            shell=True,
            text=True,
            env=os.environ,
            encoding='utf-8',
            errors='replace',
            stdout=subprocess.PIPE,
            stderr = subprocess.STDOUT,
            timeout=30,
        )
        return results.stdout

    def run(
        self,
        messages: list[dict[str, Any]],
    ):
        while True:
            lm_output = self.query_lm(messages)
            print("LM output", lm_output)
            self.history.append({
                "role": "assistant",
                "content": lm_output
            })
            action = self.parse_action(lm_output)
            print("Action", action)
            if action == "exit":
                break
            output = self.execute_action(lm_output)
            print("output", output)
            self.history.append({
                "role": "system",
                "content": output
            })
