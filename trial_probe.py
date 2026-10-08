#!/usr/bin/env python3
"""Probe Remalt account entitlements/gates by session cookie.
Usage: python trial_probe.py [email password]  (defaults: last line of accounts.jsonl)
"""
import json, sys, pathlib, urllib.request, http.cookiejar

BASE = "https://remalt.com"
ACC = pathlib.Path(__file__).parent / "accounts.jsonl"

def main():
    if len(sys.argv) >= 3:
        email, pw = sys.argv[1], sys.argv[2]
    else:
        a = json.loads(ACC.read_text(encoding="utf-8").strip().splitlines()[-1])
        email, pw = a["email"], a["password"]
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    def post(path, data):
        r = urllib.request.Request(BASE+path, data=json.dumps(data).encode(),
            headers={"Content-Type":"application/json","Origin":BASE,"User-Agent":"Mozilla/5.0"}, method="POST")
        try:
            with op.open(r, timeout=30) as resp: return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e: return e.code, e.read().decode()
    def get(path):
        r = urllib.request.Request(BASE+path, headers={"User-Agent":"Mozilla/5.0"})
        try:
            with op.open(r, timeout=30) as resp: return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e: return e.code, e.read().decode()

    s, b = post("/api/auth/sign-in/email", {"email": email, "password": pw})
    print("signin:", s, b[:120])
    s, b = get("/api/stripe/subscription")
    d = json.loads(b)
    print("entitlement:", json.dumps({k: d.get(k) for k in
        ["credits","storedCredits","access","plan","trialEligible","tokenBalance"]}, indent=1))
    s, b = post("/api/chat", {"messages":[{"role":"user","content":"hi"}]})
    print("chat gate:", s, b[:150])
    s, b = post("/api/webpage/analyze", {"url":"https://example.com"})
    print("webpage/analyze (no-plan?):", s, b[:150])
    s, b = get("/api/health")
    print("health leak:", s, b[:200])

if __name__ == "__main__":
    main()
