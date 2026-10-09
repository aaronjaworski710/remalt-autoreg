# -*- coding: utf-8 -*-
"""probe_chat.py — chat expects OpenAI-style `messages` array. Find full working shape + model names."""
import json, sys, pathlib, urllib.request, urllib.error, http.cookiejar

HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
ACC = accs[int(sys.argv[1]) if len(sys.argv) > 1 else 0]
BASE = "https://remalt.com"

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]

def req(path, data):
    r = urllib.request.Request(BASE + path, json.dumps(data).encode(), method="POST")
    r.add_header("Content-Type", "application/json")
    try:
        with op.open(r, timeout=90) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")[:800]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:800]

st, t = req("/api/auth/sign-in/email", {"email": ACC["email"], "password": ACC["password"]})
print("SIGNIN", st)

msgs = [{"role": "user", "content": "Reply with exactly: OK"}]

# 1) bare messages
st, t = req("/api/chat", {"messages": msgs})
print("\n[bare messages]", st, t[:300])

# 2) with model field
for m in ["gpt-6.1-sol", "claude-opus-5.5", "deepseek-v4-pro", "grok-4.7", "gpt-5.1", "claude-sonnet-4.5"]:
    st, t = req("/api/chat", {"messages": msgs, "model": m})
    line = t[:200].replace("\n", " ")
    print(f"[{m}]", st, line)
    if st == 200 and "OK" in t:
        print("  >>> WORKING MODEL FOUND:", m)
