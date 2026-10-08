"""Test double for stdio lifecycle races; never invokes a model or a tool."""
import json
import sys

serial = 0
turns = {}
requests = {}


def send(message):
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method, request_id, params = message.get("method"), message.get("id"), message.get("params", {})
    if method == "initialize":
        send({"id": request_id, "result": {"userAgent": "fake"}})
    elif method == "initialized":
        continue
    elif method == "account/read":
        kind = "apiKey" if "--api-account" in sys.argv else "chatgpt"
        send({"id": request_id, "result": {"account": {"type": kind}, "requiresOpenaiAuth": True}})
    elif method in {"thread/start", "thread/resume"}:
        serial += 1
        thread_id = params.get("threadId") or "fake-thread-" + str(serial)
        send({"id": request_id, "result": {"thread": {"id": thread_id}}})
    elif method == "turn/start":
        serial += 1
        thread_id, turn_id = params["threadId"], "fake-turn-" + str(serial)
        prompt = params["input"][0]["text"]
        turns[turn_id] = (thread_id, prompt)
        if "timeout-test" in prompt:
            continue
        result = {"id": request_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}}
        if "auto-test" in prompt:
            send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id,
                   "item": {"id": "answer", "type": "agentMessage", "text": "Test result"}}})
            send({"method": "turn/completed", "params": {"threadId": thread_id,
                   "turn": {"id": turn_id, "status": "completed"}}})
            send(result)  # Deliberately finish BEFORE the turn/start response.
        else:
            send(result)
            if "approval-test" in prompt or "unsupported-test" in prompt:
                server_id = 10000 + serial
                supported = "approval-test" in prompt
                method = "item/commandExecution/requestApproval" if supported else "item/tool/requestUserInput"
                detail = {"threadId": thread_id, "turnId": turn_id, "itemId": "command-" + str(serial)}
                if supported:
                    detail.update(command="echo test", cwd=params["cwd"], availableDecisions=["accept", "decline"])
                requests[server_id] = (thread_id, turn_id)
                send({"id": server_id, "method": method, "params": detail})
    elif method == "turn/interrupt":
        thread_id, prompt = turns[params["turnId"]]
        send({"id": request_id, "result": {}})
        if "ack-only-test" not in prompt:
            send({"method": "turn/completed", "params": {"threadId": thread_id,
                   "turn": {"id": params["turnId"], "status": "interrupted"}}})
    elif method is None and request_id in requests:
        thread_id, turn_id = requests.pop(request_id)
        send({"method": "serverRequest/resolved", "params": {"threadId": thread_id, "requestId": request_id}})
        send({"method": "turn/completed", "params": {"threadId": thread_id,
               "turn": {"id": turn_id, "status": "completed"}}})
    elif request_id is not None:
        send({"id": request_id, "error": {"code": -32601, "message": "Unsupported test method"}})
