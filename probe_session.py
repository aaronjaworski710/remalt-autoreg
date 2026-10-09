#!/usr/bin/env python3
"""Fresh sign-in with cookie jar; inspect set-cookie; test get-session + chat with live cookies."""
import json, urllib.request, http.cookiejar, pathlib, time

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
a = accs[-1]
print("ACC:", a["email"])

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def req(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    m = method or ("POST" if data is not None else "GET")
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json",
         "Content-Type": "application/json"}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=m)
    try:
        with opener.open(r, timeout=60) as resp:
            return resp.status, resp.read().decode()[:1500], dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:1500], dict(e.headers or {})

s, b, hd = req("/api/auth/sign-in/email", {"email": a["email"], "password": a["password"]})
print("SIGN-IN:", s, b[:300])
print("SET-COOKIE:", hd.get("Set-Cookie") or hd.get("set-cookie"))
print("JAR:", [(c.name, c.value[:20] + "...") for c in cj])

s, b, _ = req("/api/auth/get-session")
print("\nGET-SESSION:", s, b[:400])

s, b, _ = req("/api/stripe/subscription")
print("\nSUBSCRIPTION:", s, b[:400])

# try chat shapes
for payload in (
    {"message": "say hi", "model": "gpt-6.1-sol"},
    {"messages": [{"role": "user", "content": "say hi"}], "model": "gpt-6.1-sol"},
    {"messages": [{"role": "user", "content": "say hi"}]},
):
    s, b, _ = req("/api/chat", payload)
    print("\nCHAT", json.dumps(payload)[:80], "->", s, b[:400])

s, b, _ = req("/api/webpage/analyze", {"url": "https://example.com"})
print("\nANALYZE:", s, b[:400])
