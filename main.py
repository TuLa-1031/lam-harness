from openai import OpenAI
import re
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPEN_API_KEY"),
    base_url=os.getenv("OPEN_API_BASE_URL"),
    
)

def query_lm(messages):
    respones = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages
    )
    return respones.choices[0].message.content


def parse_action(lm_output: str) -> str:
    """Take LM output, return action"""
    matches = re.findall(
        r"```bash-action\s*\n(.*?)\n```",
        lm_output,
        re.DOTALL
    )
    return matches[0].strip() if matches else ""

def execute_action(command: str) -> str:
    """ Execute action, return output"""
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        env=os.environ,
        encoding='utf-8',
        errors="replace",
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        timeout=30,
    )
    return result.stdout


messages = [{
    "role": "system",
    "content": "You are a helpful assistant. When you want to run a command, wrap it in ```bash-action\n<command>\n```. To finish, run the exit command."
}, {
    "role": "user",
    "content": "List the files in the current directory"
}]

while True:
    lm_output = query_lm(messages)
    print("LM ouptut", lm_output)
    messages.append({
        "role": "assistant",
        "content": lm_output
    })
    action = parse_action(lm_output)
    print("Action", action)
    if action == "exit":
        break
    output = execute_action(action)
    print("output", output)
    messages.append({
        "role": "system",
        "content": output
    })