#!/usr/bin/env python3
"""Probe transcribe + linkedin endpoints with valid inputs (passed 400 validation without plan gate)."""
import json, urllib.request, http.cookiejar, pathlib, time

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
a = accs[-1]

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def req(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    m = method or ("POST" if data is not None else "GET")
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json",
         "Content-Type": "application/json"}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=m)
    try:
        with opener.open(r, timeout=180) as resp:
            return resp.status, resp.read().decode()[:4000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:4000]
    except Exception as e:
        return 0, str(e)[:300]

req("/api/auth/sign-in/email", {"email": a["email"], "password": a["password"]})

# LinkedIn post generation — topic >= 5 words
payloads = [
    {"topic": "How AI agents automate daily developer workflows and boost productivity"},
    {"topic": "How AI agents automate daily developer workflows and boost productivity",
     "tone": "professional", "platform": "linkedin"},
]
for p in payloads:
    s, b = req("/api/linkedin/generate-post", p)
    print(f"== LINKEDIN {json.dumps(p)[:90]}: {s}")
    print(b[:1200])
    print()

# Transcribe — real short YouTube video (first 60s of a classic)
s, b = req("/api/transcribe", {"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"})
print(f"== TRANSCRIBE: {s}")
print(b[:1200])
print()

# check subscription after calls (did credits move?)
s, b = req("/api/stripe/subscription")
print(f"== SUBSCRIPTION AFTER: {s}")
print(b[:800])
