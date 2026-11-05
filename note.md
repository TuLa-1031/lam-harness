User start with a prompt, the agent propose an action, exe the action, tell the LM the output, repeat


## Pseudocode

```messages = [{"role": "user", "content": "Help me fix the ValueError in main.py}]
while True:
    lm_output = query_lm(messages)
    print("LM output", output)
    messages.append({"role": "assistent", "content": lm_output}) # remember what the LM said
    action = parse_action(lm_output) #seperate the action from output
    print("Action", action)
    if action == "exit":
        break
    output = execute_action(action)
    print("Output": output)
    messages.append({"role": "user", "content": output}) # send command output back```