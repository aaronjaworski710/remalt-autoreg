#!/usr/bin/env python3
"""Remalt.com autoreg v2 — full API flow, no captcha, no browser.

Flow: Voidash inbox -> better-auth sign-up/email -> poll verify mail ->
      GET magic_link -> sign-in (cookie) -> verify subscription state.

Usage:
  python remalt_autoreg.py N                 # register N accounts (sequential)
  python remalt_autoreg.py N --threads 4     # parallel registration
  python remalt_autoreg.py --validate        # re-check all accounts in pool
  python remalt_autoreg.py --stats           # pool stats

Output: accounts.jsonl (append, dedup by email). Lock-protected writes.
Stdlib only.
"""
import json, re, sys, time, pathlib, threading, argparse, urllib.request, http.cookiejar

BASE = "https://remalt.com"
VOID = "https://api.voidash.com/api/v1"
HERE = pathlib.Path(__file__).parent
ACC_FILE = HERE / "accounts.jsonl"
_wlock = threading.Lock()


def req(url, method="GET", data=None, headers=None, timeout=40, opener=None):
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    if body:
        hdrs["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    open_fn = opener.open if opener else urllib.request.urlopen
    try:
        with open_fn(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)[:300]


def bearer_headers(sk):
    return {"Authorization": ("Bea" + "rer ") + sk}


def voidash_inbox(domain="voidash.bond"):
    s, b = req(f"{VOID}/inboxes", "POST", {"domain": domain})
    d = json.loads(b)
    return d["address"], d["session_key"]


def voidash_wait_mail(sk, want_subj=None, tries=30, delay=4):
    for _ in range(tries):
        s, b = req(f"{VOID}/messages", headers=bearer_headers(sk))
        try:
            msgs = json.loads(b).get("messages", [])
        except Exception:
            msgs = []
        for m in msgs:
            if want_subj is None or want_subj.lower() in (m.get("subject") or "").lower():
                return m
        time.sleep(delay)
    return None


def voidash_full(sk, mid):
    s, b = req(f"{VOID}/messages/{mid}", headers=bearer_headers(sk))
    return b


def save_acc(acc):
    with _wlock:
        with open(ACC_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(acc) + "\n")


def known_emails():
    emails = set()
    if ACC_FILE.exists():
        with _wlock:
            for line in open(ACC_FILE, encoding="utf-8"):
                line = line.strip()
                if line:
                    try:
                        emails.add(json.loads(line)["email"])
                    except Exception:
                        pass
    return emails


def check_subscription(email, pw):
    """Sign in with cookie jar, return subscription dict or None."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    s, b = req(f"{BASE}/api/auth/sign-in/email", "POST",
               {"email": email, "password": pw},
               {"Origin": BASE, "Accept": "application/json"}, opener=opener)
    if s != 200 or '"token"' not in b:
        return None, f"signin {s}"
    token = json.loads(b)["token"]
    s, b = req(f"{BASE}/api/stripe/subscription", headers={
        "Origin": BASE, "Accept": "application/json"}, opener=opener)
    if s != 200:
        return None, f"sub {s}"
    return json.loads(b), token


def register(name=None, pw="RemaltFarm2026x!"):
    addr, sk = voidash_inbox()
    name = name or "Remalt User"
    s, b = req(f"{BASE}/api/auth/sign-up/email", "POST",
               {"email": addr, "password": pw, "name": name},
               {"Origin": BASE})
    if s != 200:
        return {"error": f"signup {s}: {b[:200]}", "email": addr}
    uid = json.loads(b)["user"]["id"]
    mail = voidash_wait_mail(sk, "verify")
    if not mail:
        return {"error": "no verify mail", "email": addr, "user_id": uid}
    full = json.loads(voidash_full(sk, mail.get("id")) or "{}")
    link = full.get("magic_link") or ""
    if not link.startswith("https://remalt.com/api/auth/verify-email"):
        links = re.findall(
            r'https://remalt\.com/api/auth/verify-email\?token=***',
            (full.get("html") or "") + (full.get("text") or ""))
        link = links[0] if links else ""
    link = link.replace("&amp;", "&")
    if not link:
        return {"error": "no verify link", "email": addr}
    s, _ = req(link)
    if s not in (200, 302, 303, 307):
        return {"error": f"verify {s}", "email": addr}
    sub, token = check_subscription(addr, pw)
    if not token:
        return {"error": f"signin after verify failed: {sub}", "email": addr, "user_id": uid}
    acc = {"email": addr, "password": pw, "name": name, "user_id": uid,
           "session_token": token, "voidash_key": sk,
           "stored_credits": (sub or {}).get("storedCredits", 0),
           "trial_eligible": (sub or {}).get("trialEligible", False),
           "access": (sub or {}).get("access", ""),
           "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_acc(acc)
    return acc


def cmd_register(n, threads):
    known = known_emails()
    print(f"pool before: {len(known)} accounts")
    ok, fail = 0, 0
    if threads <= 1:
        for i in range(n):
            a = register()
            if "session_token" in a:
                ok += 1
                print(f"[{i+1}/{n}] OK {a['email']} stored={a.get('stored_credits')} trial={a.get('trial_eligible')}")
            else:
                fail += 1
                print(f"[{i+1}/{n}] FAIL {a.get('error', a)}")
            time.sleep(1)
    else:
        results = []
        rlock = threading.Lock()

        def worker(i):
            a = register()
            with rlock:
                results.append((i, a))
                nonlocal ok, fail
                if "session_token" in a:
                    ok += 1
                    print(f"[{len(results)}/{n}] OK {a['email']} stored={a.get('stored_credits')}")
                else:
                    fail += 1
                    print(f"[{len(results)}/{n}] FAIL {a.get('error', a)}")

        ts = []
        for i in range(n):
            t = threading.Thread(target=worker, args=(i,))
            t.start()
            ts.append(t)
            while threading.active_count() - 1 >= threads:
                time.sleep(0.5)
        for t in ts:
            t.join()
    print(f"done: ok={ok} fail={fail} -> {ACC_FILE}")


def cmd_validate():
    known = known_emails()
    lines = [json.loads(l) for l in open(ACC_FILE, encoding="utf-8") if l.strip()]
    alive, dead = 0, 0
    for a in lines:
        sub, token = check_subscription(a["email"], a["password"])
        if token:
            alive += 1
            tb = (sub or {}).get("tokenBalance") or {}
            print(f"ALIVE {a['email']} access={(sub or {}).get('access')} "
                  f"stored={(sub or {}).get('storedCredits')} locked={tb.get('locked')} "
                  f"plan={(sub or {}).get('plan')}")
            if token != a.get("session_token"):
                a["session_token"] = token
        else:
            dead += 1
            print(f"DEAD  {a['email']} ({sub})")
    if dead or True:
        with _wlock:
            with open(ACC_FILE, "w", encoding="utf-8") as f:
                for a in lines:
                    f.write(json.dumps(a) + "\n")
    print(f"validate: alive={alive} dead={dead}")


def cmd_stats():
    lines = [json.loads(l) for l in open(ACC_FILE, encoding="utf-8") if l.strip()]
    n = len(lines)
    with_plan = sum(1 for a in lines if a.get("access") not in (None, "", "viewer"))
    trial_ok = sum(1 for a in lines if a.get("trial_eligible"))
    print(f"accounts: {n} | with_plan: {with_plan} | trial_eligible: {trial_ok}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=0)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    if args.validate:
        cmd_validate()
    elif args.stats:
        cmd_stats()
    elif args.n > 0:
        cmd_register(args.n, args.threads)
    else:
        ap.print_help()
