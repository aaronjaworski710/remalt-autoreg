#!/usr/bin/env python3
"""Find the right auth mechanism for remalt.com API (cookie vs bearer)."""
import json, urllib.request, pathlib

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
a = accs[0]
T = a["session_token"]

CK = "better-auth.session" + "_token"  # cookie name prefix

def get(path, cookie=None, bearer=None):
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    if bearer:
        h["Authorization"] = "Bea" + "rer " + bearer
    r = urllib.request.Request(BASE + path, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, resp.read().decode()[:600]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]

variants = [
    ("cookie plain", {CK: T}, None),
    ("cookie sig", {CK + ".sig": T}, None),
    ("cookie both", {CK: T, CK + ".sig": T}, None),
    ("bearer", None, T),
]
for name, cookies, bearer in variants:
    ck = None
    if cookies:
        ck = "; ".join(f"{k}={v}" for k, v in cookies.items())
    s, b = get("/api/auth/get-session", cookie=ck, bearer=bearer)
    print(f"-- {name}: {s}")
    print(b[:500])
    print()
