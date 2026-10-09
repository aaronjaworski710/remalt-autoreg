#!/usr/bin/env python3
"""Probe razorpay trial activation flow with signed-in session."""
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

probes = [
    ("POST", "/api/razorpay/order", {"plan": "starter_promo"}),
    ("POST", "/api/razorpay/order", {"plan": "starter", "promo": "starter_promo"}),
    ("POST", "/api/razorpay/order", {}),
    ("GET",  "/api/razorpay/plans", None),
    ("POST", "/api/trial/activate", {}),
    ("POST", "/api/trial", {}),
    ("POST", "/api/subscription/trial", {}),
    ("POST", "/api/stripe/trial", {}),
    ("POST", "/api/stripe/checkout", {"plan": "starter", "trial": True}),
    ("GET",  "/api/stripe/plans", None),
    ("POST", "/api/stripe/subscription", {"plan": "starter", "trial": True}),
]
for m, p, d in probes:
    s, b = req(p, d, method=m)
    tag = "HTML-404" if b.startswith("<!DOCTYPE") else b[:400]
    print(f"== {m} {p} {json.dumps(d) if d else ''}: {s}\n{tag}\n")
