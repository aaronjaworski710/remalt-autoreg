# -*- coding: utf-8 -*-
"""probe_full.py — finish API reverse: model list, chat w/ models, coins, brainboard, image, transcribe, linkedin, user endpoints."""
import json, sys, pathlib, urllib.request, urllib.parse, urllib.error, http.cookiejar

HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
IDX = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ACC = accs[IDX % len(accs)]
BASE = "https://remalt.com"

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]

def req(method, path, data=None, raw=False):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, body, method=method)
    if body:
        r.add_header("Content-Type", "application/json")
    try:
        with op.open(r, timeout=30) as resp:
            t = resp.read().decode("utf-8", "replace")
            return resp.status, t[:600]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]
    except Exception as e:
        return -1, str(e)[:200]

# sign-in
st, t = req("POST", "/api/auth/sign-in/email", {"email": ACC["email"], "password": ACC["password"]})
print("SIGNIN", st, ("ok" if st == 200 else t[:120]))

print("\n=== GET endpoints ===")
for p in ["/api/user/credits", "/api/credits", "/api/coins", "/api/user", "/api/user/profile",
          "/api/subscription", "/api/stripe/subscription", "/api/models", "/api/config",
          "/api/brainboard", "/api/brainboards", "/api/history", "/api/generations",
          "/api/transcribe", "/api/settings", "/api/plans", "/api/pricing", "/api/stripe/plans",
          "/api/razorpay/plans", "/api/usage", "/api/stats", "/api/version", "/api/features"]:
    st, t = req("GET", p)
    flag = "OK " if st == 200 and t and t != "null" else "   "
    print(flag, st, p, "→", t[:110].replace("\n", " "))

print("\n=== POST probes (small payloads) ===")
# chat with model variants
for model in ["gpt-6.1-sol", "claude-opus-5.5", "deepseek-v4-pro", "grok-4.7"]:
    st, t = req("POST", "/api/chat", {"message": "Say OK", "model": model})
    print("chat", model, "→", st, t[:150].replace("\n", " "))

st, t = req("POST", "/api/image/generate", {"prompt": "red dot", "model": "gpt-image-2.5"})
print("image →", st, t[:150].replace("\n", " "))
st, t = req("POST", "/api/linkedin/generate-post", {"topic": "AI"})
print("linkedin →", st, t[:150].replace("\n", " "))
st, t = req("POST", "/api/brainboard/run", {"nodes": []})
print("brainboard/run →", st, t[:150].replace("\n", " "))
st, t = req("POST", "/api/transcribe", {"url": "https://example.com/a.mp3"})
print("transcribe →", st, t[:150].replace("\n", " "))
st, t = req("POST", "/api/webpage/analyze", {"url": "https://example.com"})
print("analyze →", st, t[:200].replace("\n", " "))
