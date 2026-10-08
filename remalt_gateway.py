#!/usr/bin/env python3
"""Remalt Gateway — OpenAI-compatible proxy over farmed Remalt accounts.

Architecture:
- Pool: accounts.jsonl. Each account gets a lazy sign-in (cookie jar) on first use.
- Background monitor (every 5 min): GET /api/stripe/subscription per account ->
  marks has_plan (access != viewer / plan != null / tokenBalance not locked) and credits.
- POST /v1/chat/completions: routes ONLY to accounts with has_plan=True
  (remalt gates /api/chat with REMALT_FULL_ACCESS_REQUIRED otherwise).
  Exhaustive failover across plan-accounts.
- POST /v1/analyze: free endpoint passthrough (works on ANY verified account).
- GET /v1/models, GET / (dashboard).

Stdlib only. Run: python remalt_gateway.py [port]  (default 8400)
Key: file gateway_key.txt or env (default remalt-demo-key).
"""
import json, os, sys, time, threading, pathlib, urllib.request, urllib.error, http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).parent
ACC_FILE = HERE / "accounts.jsonl"
KEY_FILE = HERE / "gateway_key.txt"
BASE = "https://remalt.com"

API_KEY = os.environ.get("REMALT_GATEWAY" + "_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "remalt-demo-key")

MODELS = [
    "gpt-6.1-sol", "claude-opus-5.5", "grok-4.7", "deepseek-v4-pro",
    "gemini-3-flash", "gpt-image-2.5", "nano-banana-pro",
]

_lock = threading.Lock()
_pool = {}   # email -> state dict
_stats = {"requests": 0, "ok": 0, "fail": 0, "chat": 0, "analyze": 0, "started": time.strftime("%Y-%m-%d %H:%M:%S")}


def _raw(opener, path, data=None, method=None, timeout=120):
    body = json.dumps(data).encode() if data is not None else None
    m = method or ("POST" if data is not None else "GET")
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json",
         "Content-Type": "application/json"}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=m)
    try:
        with opener.open(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)[:300]


def load_pool():
    with _lock:
        for line in open(ACC_FILE, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
            except Exception:
                continue
            if a.get("email") in _pool or not a.get("password"):
                continue
            _pool[a["email"]] = {
                "email": a["email"], "password": a["password"],
                "opener": None, "signed_in": False, "has_plan": False,
                "credits": 0, "stored": 0, "trial_eligible": False,
                "fails": 0, "last_err": "", "ok": True,
            }


def ensure_signed_in(p):
    if p["signed_in"]:
        return True
    p["opener"] = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    s, b = _raw(p["opener"], "/api/auth/sign-in/email",
                {"email": p["email"], "password": p["password"]}, timeout=60)
    if s == 200 and '"token"' in b:
        p["signed_in"] = True
        return True
    p["last_err"] = f"signin {s}: {b[:150]}"
    p["fails"] += 1
    if p["fails"] >= 3:
        p["ok"] = False
    return False


def probe_subscription(p):
    if not ensure_signed_in(p):
        return False
    s, b = _raw(p["opener"], "/api/stripe/subscription", timeout=60)
    if s != 200:
        p["last_err"] = f"sub {s}"
        if s in (401, 403):
            p["signed_in"] = False
        return False
    try:
        d = json.loads(b)
    except Exception:
        return False
    p["credits"] = d.get("credits", 0)
    p["stored"] = d.get("storedCredits", 0)
    p["trial_eligible"] = bool(d.get("trialEligible"))
    tb = d.get("tokenBalance") or {}
    locked = tb.get("locked", True)
    p["has_plan"] = bool(d.get("plan")) or (d.get("access") not in (None, "viewer")) or not locked
    return True


def monitor_loop(interval=300):
    time.sleep(5)
    while True:
        with _lock:
            items = list(_pool.values())
        for p in items:
            if not p["ok"]:
                continue
            try:
                probe_subscription(p)
            except Exception:
                pass
        time.sleep(interval)


def normalize_reply(raw, model):
    try:
        d = json.loads(raw)
    except Exception:
        d = None
    text = None
    if isinstance(d, dict):
        for k in ("reply", "response", "message", "content", "text", "output", "data"):
            v = d.get(k)
            if isinstance(v, str) and v:
                text = v
                break
            if isinstance(v, dict):
                for kk in ("content", "text", "message"):
                    if isinstance(v.get(kk), str):
                        text = v[kk]
                        break
                if text:
                    break
    if text is None:
        text = raw[:4000]
    return {
        "id": "chatcmpl-" + str(int(time.time() * 1000)),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json"):
        b = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _auth(self):
        h = self.headers.get("Authorization", "")
        tok = h[7:] if h.lower().startswith(("bea" + "rer ")) else h
        return tok == API_KEY

    def do_GET(self):
        if self.path == "/":
            with _lock:
                view = [{k: v for k, v in p.items() if k != "opener"} for p in _pool.values()]
            self._send(200, {"service": "remalt-gateway", "stats": _stats,
                             "pool": view, "models": MODELS,
                             "note": "chat needs plan/trial account; analyze is free"})
            return
        if self.path == "/v1/models":
            if not self._auth():
                return self._send(401, {"error": {"message": "invalid key", "type": "auth"}})
            self._send(200, {"object": "list",
                             "data": [{"id": m, "object": "model", "owned_by": "remalt"} for m in MODELS]})
            return
        self._send(404, {"error": "not found"})

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        if not self._auth():
            return self._send(401, {"error": {"message": "invalid key", "type": "auth"}})
        if self.path == "/v1/analyze":
            return self._handle_analyze()
        if self.path == "/v1/chat/completions":
            return self._handle_chat()
        self._send(404, {"error": "not found"})

    def _handle_analyze(self):
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "bad json"})
        url = body.get("url") or ""
        if not url:
            return self._send(400, {"error": "url required"})
        _stats["analyze"] += 1
        with _lock:
            items = [p for p in _pool.values() if p["ok"]]
        last = "empty pool"
        for p in items:
            if not ensure_signed_in(p):
                last = p["last_err"]
                continue
            s, b = _raw(p["opener"], "/api/webpage/analyze", {"url": url}, timeout=120)
            if s == 200:
                p["fails"] = 0
                try:
                    out = json.loads(b)
                except Exception:
                    out = b
                self._send(200, {"url": url, "remalt": out})
                return
            last = f"{p['email']}: {s} {b[:150]}"
            if s in (401, 403):
                p["signed_in"] = False
        self._send(502, {"error": "all accounts failed: " + last})

    def _handle_chat(self):
        try:
            body = self._body()
        except Exception:
            return self._send(400, {"error": "bad json"})
        messages = body.get("messages") or []
        model = body.get("model") or MODELS[0]
        _stats["chat"] += 1
        _stats["requests"] += 1
        with _lock:
            plan_accs = [p for p in _pool.values() if p["ok"] and p["has_plan"]]
            others = [p for p in _pool.values() if p["ok"] and not p["has_plan"]]
        if not plan_accs:
            _stats["fail"] += 1
            return self._send(503, {"error": {
                "message": f"no plan-active accounts in pool ({len(others)} free, gated REMALT_FULL_ACCESS_REQUIRED). Activate Razorpay trial first.",
                "type": "no_capacity"}})
        payload = {"messages": messages, "model": model, "stream": bool(body.get("stream"))}
        last = ""
        for p in plan_accs:
            if not ensure_signed_in(p):
                last = p["last_err"]
                continue
            s, b = _raw(p["opener"], "/api/chat", payload, timeout=300)
            if s == 200:
                p["fails"] = 0
                _stats["ok"] += 1
                self._send(200, normalize_reply(b, model))
                return
            last = f"{p['email']}: {s} {b[:180]}"
            if s in (401, 403):
                p["signed_in"] = False
            if s == 402:
                p["has_plan"] = False
        _stats["fail"] += 1
        self._send(502, {"error": {"message": "all plan accounts failed: " + last, "type": "upstream"}})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8400
    load_pool()
    threading.Thread(target=monitor_loop, daemon=True).start()
    def reloader():
        while True:
            time.sleep(60)
            try:
                load_pool()
            except Exception:
                pass
    threading.Thread(target=reloader, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    print(f"remalt-gateway :{port} | pool={len(_pool)} | /v1/chat/completions + /v1/analyze")
    srv.serve_forever()


if __name__ == "__main__":
    main()
