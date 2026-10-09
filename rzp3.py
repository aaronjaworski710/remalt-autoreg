# -*- coding: utf-8 -*-
"""Click 'Start Starter trial' as logged-in user, handle whatever payment opens."""
import json, time, pathlib, sys, urllib.request, http.cookiejar
BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
SHOTS = HERE / "shots_trial"
SHOTS.mkdir(exist_ok=True)
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
cards = json.load(open(HERE / "cards.json", encoding="utf-8"))
ci = int(sys.argv[1]) if len(sys.argv) > 1 else 0
a = accs[-1]
card = cards[ci]
print("acc:", a["email"], "| card:", card["number"][:6], card["exp"])

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def api(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json", "Content-Type": "application/json"}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method="POST" if data is not None else "GET")
    try:
        with opener.open(r, timeout=60) as resp: return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
s,b = api("/api/auth/sign-in/email", {"email": a["email"], "password": a["password"]})
ck = {c.name: c.value for c in cj}
print("signin:", s)

from camoufox.sync_api import Camoufox
with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
    page.context.add_cookies([{"name": k, "value": v, "domain": ".remalt.com", "path": "/"} for k,v in ck.items()])
    page.goto(BASE + "/pricing", timeout=60000, wait_until="domcontentloaded")
    time.sleep(6)
    page.locator('button:has-text("Start Starter trial")').first.click(timeout=10000)
    print("TRIAL CLICKED")
    result = "TIMEOUT"
    for i in range(40):
        time.sleep(3)
        url = page.url
        if i % 3 == 0:
            page.screenshot(path=str(SHOTS / f"t{i:02d}.png"))
            try: body = page.locator("body").inner_text()[:250].replace("\n"," | ")
            except Exception: body = "?"
            print(f"[{i*3}s] url={url[:90]}")
            print("   ", body)
        # Razorpay widget?
        for f in page.frames:
            if "razorpay" in (f.url or ""):
                print("RAZORPAY FRAME:", f.url[:120])
                try:
                    f.locator('input[autocomplete="cc-number"]').first.fill(card["number"], timeout=6000)
                    f.locator('input[autocomplete="cc-exp"]').first.fill(card["exp"][:2]+card["exp"][2:], timeout=6000)
                    f.locator('input[autocomplete="cc-csc"], input[name="cvv"]').first.fill(card["cvv"], timeout=6000)
                    page.screenshot(path=str(SHOTS / "card_filled.png"))
                    f.locator('button:has-text("Pay"), button[type="submit"]').first.click(timeout=6000)
                    print("PAY CLICKED")
                except Exception as e:
                    print("rzp fill err:", str(e)[:120])
                break
        if "checkout.stripe.com" in url:
            result = "STRIPE"
            print(">>> Stripe checkout opened (see hit_stripe)")
            break
        low = page.locator("body").inner_text().lower() if page.url.startswith(BASE) else ""
        if "welcome" in low or "success" in low or "activated" in low:
            result = "SUCCESS"
            print(">>> SUCCESS:", low[:300])
            break
    page.screenshot(path=str(SHOTS / "final.png"))
    print("RESULT:", result)
    json.dump({"result": result, "url": page.url}, open(HERE / "trial_result.json", "w"))
s,b = api("/api/stripe/subscription")
print("VERIFY:", s, b[:400])
