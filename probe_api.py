#!/usr/bin/env python3
"""Probe remalt.com API surface with a live session token."""
import json, sys, pathlib, urllib.request

BASE = "https://remalt.com"
ACC = pathlib.Path(__file__).parent / "accounts.jsonl"

def load_acc(i=0):
    accs = [json.loads(l) for l in open(ACC, encoding="utf-8") if l.strip()]
    return accs[i]

def req(path, method="GET", data=None, token=None, extra_headers=None, timeout=40):
    hdrs = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json"}
    if token:
        hdrs["Authorization"] = ("Bea" + "rer ") + token
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        hdrs["Content-Type"] = "application/json"
    if extra_headers:
        hdrs.update(extra_headers)
    r = urllib.request.Request(BASE + path, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")[:2000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:2000]
    except Exception as e:
        return 0, str(e)[:500]

if __name__ == "__main__":
    a = load_acc(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    t = a["session_token"]
    print("ACC:", a["email"])
    probes = [
        ("GET", "/api/auth/get-session", None),
        ("GET", "/api/stripe/subscription", None),
        ("GET", "/api/user/credits", None),
        ("GET", "/api/user", None),
        ("GET", "/api/models", None),
        ("GET", "/api/config", None),
        ("POST", "/api/chat", {"message": "hi", "model": "gpt-6.1-sol"}),
        ("POST", "/api/chat", {"messages": [{"role": "user", "content": "hi"}]}),
        ("POST", "/api/webpage/analyze", {"url": "https://example.com"}),
        ("GET", "/api/razorpay/config", None),
        ("GET", "/api/razorpay/key", None),
        ("POST", "/api/razorpay/order", {"plan": "starter_promo"}),
        ("GET", "/api/health", None),
    ]
    for m, p, d in probes:
        s, b = req(p, m, d, token=t)
        print(f"\n== {m} {p} -> {s}")
        print(b[:1200])
