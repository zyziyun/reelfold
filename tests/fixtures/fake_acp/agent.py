"""A stand-in coding agent that speaks the Agent Client Protocol (JSON-RPC 2.0, one object per line on stdio).

No account, no network: tests install it under an agent's program name (``qwen``, ``kimi``, ``cursor-agent`` ...).
FAKE_ACP picks a behaviour (comma-separated):
  ok (default)   models via the older ``models`` list; a thought, a tool call that asks permission, then the answer
  config         models via ``configOptions`` (category model) instead
  auth           session/new -> auth_required (-32000): not signed in
  cursor-auth    session/new -> auth_required until ``authenticate`` with method cursor_login
  region         session/prompt -> "User location is not supported for the API use."
  old-args       ``--acp`` is an unknown argument (exits 1); ``--experimental-acp`` / ``acp`` work
  hang           session/prompt never answers
  crash          exits in the middle of session/prompt
  refusal        stopReason refusal
FAKE_ACP_LOG: a file each request (method, params, argv, which API-key variables it was given) is appended to.
"""
import json
import os
import sys
import time

MODE = set((os.environ.get("FAKE_ACP") or "ok").split(","))
LOG = os.environ.get("FAKE_ACP_LOG")
KEYS = sorted(k for k in os.environ if k.endswith(("_API_KEY", "_AUTH_TOKEN")) or k.startswith("OPENAI_"))
state = dict(model="fake-small", authed=False, perm=None)


def log(rec):
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def read():
    ln = sys.stdin.readline()
    if not ln:
        sys.exit(0)
    return json.loads(ln)


def update(sid, u):
    send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": u}})


def text_of(blocks):
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def handle(msg):
    m, p, rid = msg.get("method"), msg.get("params") or {}, msg.get("id")
    log(dict(method=m, params=p, argv=sys.argv[1:], keys=KEYS, cwd=os.getcwd()))
    if m == "initialize":
        return {"protocolVersion": 1, "agentInfo": {"name": "fake-agent", "version": "9.9.9"},
                "agentCapabilities": {"promptCapabilities": {"image": True}},
                "authMethods": [{"id": "cursor_login", "name": "Cursor login"}]}
    if m == "authenticate":
        state["authed"] = p.get("methodId") == "cursor_login"
        return {}
    if m == "session/new":
        if "auth" in MODE or ("cursor-auth" in MODE and not state["authed"]):
            return {"__error__": {"code": -32000, "message": "Authentication required"}}
        models = [{"modelId": "fake-small", "name": "Fake Small"}, {"modelId": "fake-big", "name": "Fake Big"}]
        if "config" in MODE:
            return {"sessionId": "s1", "configOptions": [{"id": "model", "name": "Model", "category": "model",
                                                          "type": "select", "currentValue": state["model"],
                                                          "options": [{"value": x["modelId"], "name": x["name"]}
                                                                      for x in models]}]}
        return {"sessionId": "s1", "models": {"availableModels": models, "currentModelId": state["model"]}}
    if m == "session/set_model":
        state["model"] = p["modelId"]
        return {}
    if m == "session/set_config_option":
        state["model"] = p["value"]
        return {}
    if m == "session/prompt":
        sid = p["sessionId"]
        if "hang" in MODE:
            time.sleep(3600)
        if "crash" in MODE:
            sys.stderr.write("fatal: something broke\n")
            sys.stderr.flush()
            os._exit(3)
        if "region" in MODE:
            return {"__error__": {"code": -32603, "message": "User location is not supported for the API use."}}
        update(sid, {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "thinking..."}})
        update(sid, {"sessionUpdate": "tool_call", "toolCallId": "t1", "title": "Read secrets.txt", "kind": "read",
                     "status": "pending"})
        send({"jsonrpc": "2.0", "id": "perm-1", "method": "session/request_permission", "params": {
            "sessionId": sid, "toolCall": {"toolCallId": "t1", "title": "Read secrets.txt"},
            "options": [{"optionId": "yes", "name": "Allow", "kind": "allow_once"},
                        {"optionId": "no", "name": "Reject", "kind": "reject_once"}]}})
        while True:                                   # the client's answer to the permission request
            r = read()
            if r.get("id") == "perm-1" and "method" not in r:
                state["perm"] = ((r.get("result") or {}).get("outcome") or {}).get("optionId") or "cancelled"
                log(dict(method="permission-answer", params=r))
                break
            handle_and_reply(r)
        if "refusal" in MODE:
            return {"stopReason": "refusal"}
        prompt = text_of(p.get("prompt") or [])
        images = sum(1 for b in p.get("prompt") or [] if b.get("type") == "image")
        if "JSON" in prompt:
            reply = json.dumps({"ok": True, "sum": 4, "model": state["model"], "perm": state["perm"],
                                "images": images})
        else:
            reply = f"hello from {state['model']}"
        for i in range(0, len(reply), 7):            # streamed in chunks
            update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": reply[i:i + 7]}})
        return {"stopReason": "end_turn", "usage": {"inputTokens": 12, "outputTokens": 5}}
    if m == "session/cancel":
        return None
    return {"__error__": {"code": -32601, "message": f"no {m}"}}


def handle_and_reply(msg):
    res = handle(msg)
    if "id" not in msg or msg.get("method") is None:
        return
    if isinstance(res, dict) and "__error__" in res:
        send({"jsonrpc": "2.0", "id": msg["id"], "error": res["__error__"]})
    else:
        send({"jsonrpc": "2.0", "id": msg["id"], "result": res or {}})


def main():
    if "old-args" in MODE and "--acp" in sys.argv[1:]:
        # like Gemini CLI 0.28: the complaint first, then the whole help
        sys.stderr.write("Unknown argument: acp\nUsage: agent [options]\n" +
                         "".join(f"  --option-{i}    what it does  [boolean]\n" for i in range(40)))
        sys.exit(1)
    if "--version" in sys.argv[1:]:
        print("fake-agent 9.9.9")
        return
    sys.stdout.write("starting fake agent (a log line on stdout)\n")
    sys.stdout.flush()
    while True:
        handle_and_reply(read())


if __name__ == "__main__":
    main()
