#!/usr/bin/env python3
"""Probe razorpay order with correct field name 'item'."""
import json, urllib.request, http.cookiejar, pathlib

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
        with opener.open(r, timeout=60) as resp:
            return resp.status, resp.read().decode()[:3000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:3000]
    except Exception as e:
        return 0, str(e)[:300]

req("/api/auth/sign-in/email", {"email": a["email"], "password": a["password"]})

for d in ({"item": "starter_promo"}, {"item": "starter"}, {"item": "refill_450"}):
    s, b = req("/api/razorpay/order", d)
    print(f"== razorpay order {d}: {s}\n{b[:1500]}\n")

s, b = req("/api/stripe/checkout", {"item": "starter"})
print(f"== stripe checkout starter: {s}\n{b[:800]}\n")
