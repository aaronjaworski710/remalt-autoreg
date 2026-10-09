# -*- coding: utf-8 -*-
"""Razorpay starter_promo trial activation: API order -> camoufox checkout widget -> card."""
import json, time, pathlib, sys, urllib.request, http.cookiejar

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
SHOTS = HERE / "shots_rzp"
SHOTS.mkdir(exist_ok=True)

accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
cards = json.load(open(HERE / "cards.json", encoding="utf-8"))
ci = int(sys.argv[1]) if len(sys.argv) > 1 else 0
a = accs[-1]
card = cards[ci]
print("acc:", a["email"], "| card idx:", ci, card["number"][:6], card["exp"])

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def api(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    h = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Accept": "application/json",
         "Content-Type": "application/json"}
    r = urllib.request.Request(BASE + path, data=body, headers=h,
                               method="POST" if data is not None else "GET")
    try:
        with opener.open(r, timeout=60) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

s, b = api("/api/auth/sign-in/email", {"email": a["email"], "password": a["password"]})
print("signin:", s)
s, b = api("/api/razorpay/order", {"item": "starter_promo"})
print("order:", s)
o = json.loads(b)
print(json.dumps(o)[:300])
ck = {c.name: c.value for c in cj}

from camoufox.sync_api import Camoufox

with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
    page.context.add_cookies([{"name": k, "value": v, "domain": ".remalt.com", "path": "/"} for k, v in ck.items()])
    page.goto(BASE + "/pricing", timeout=60000, wait_until="domcontentloaded")
    time.sleep(5)
    # load razorpay checkout.js
    page.evaluate("""() => new Promise((res) => {
        const s = document.createElement('script');
        s.src = 'https://checkout.razorpay.com/v1/checkout.js';
        s.onload = () => res('loaded'); s.onerror = () => res('error');
        document.head.appendChild(s);
    })""")
    time.sleep(3)
    print("open checkout widget")
    page.evaluate("""(o) => {
        window.__rzp_done = null; window.__rzp_fail = null;
        const rz = new Razorpay({
            key: o.key, subscription_id: o.subscriptionId,
            name: o.name, description: o.description, currency: o.currency,
            prefill: o.prefill,
            handler: (resp) => { window.__rzp_done = resp; },
        });
        rz.on('payment.failed', (r) => { window.__rzpFail = r.error; });
        rz.open();
    }""", {k: o[k] for k in ("key", "subscriptionId", "name", "description", "currency", "prefill")})
    time.sleep(8)
    page.screenshot(path=str(SHOTS / "01_widget.png"))
    # widget is in iframe; camoufox frames
    fr = None
    for f in page.frames:
        if "razorpay" in (f.url or "") or "checkout" in (f.url or ""):
            fr = f; break
    print("frame:", (fr.url[:100] if fr else None))
    if not fr:
        # maybe inline popup — check DOM
        html = page.content()
        print("razorpay div in page:", "razorpay" in html.lower())
        page.screenshot(path=str(SHOTS / "01b_noframe.png"))
        fr = page.main_frame
    def ffill(sel, val):
        try:
            loc = fr.locator(sel).first
            loc.wait_for(state="visible", timeout=8000)
            loc.fill(val)
            print("filled", sel)
            return True
        except Exception as e:
            print("miss", sel, str(e)[:80])
            return False
    ffill('input[autocomplete="cc-number"], input[name="card_number"], input[placeholder*="card" i]', card["number"])
    ffill('input[autocomplete="cc-exp"], input[name="expiry"], input[placeholder*="MM" i]', card["exp"][:2] + card["exp"][2:])
    ffill('input[autocomplete="cc-csc"], input[name="cvv"], input[placeholder*="CVV" i]', card["cvv"])
    time.sleep(2)
    page.screenshot(path=str(SHOTS / "02_card.png"))
    try:
        fr.locator('button:has-text("Pay"), input[type="submit"]').first.click(timeout=8000)
        print("PAY CLICKED")
    except Exception as e:
        print("pay click fail", str(e)[:100])
    result = "TIMEOUT"
    for i in range(30):
        time.sleep(3)
        try:
            done = page.evaluate("() => window.__rzp_done")
            fail = page.evaluate("() => window.__rzpFail")
        except Exception:
            done = fail = None
        if i % 3 == 0:
            page.screenshot(path=str(SHOTS / f"03_w{i:02d}.png"))
            print(f"[{i*3}s] done={bool(done)} fail={fail}")
        if done:
            result = "PAID"
            print(">>> PAYMENT DONE:", json.dumps(done)[:300])
            break
        if fail:
            result = "FAILED"
            print(">>> FAILED:", json.dumps(fail)[:400])
            break
    page.screenshot(path=str(SHOTS / "04_final.png"))
    json.dump({"result": result}, open(HERE / "rzp_result.json", "w"))
    time.sleep(5)
    s, b = api("/api/stripe/subscription")
    print("VERIFY:", s, b[:400])
    # if payment done, tell remalt
    if result == "PAID":
        s2, b2 = api("/api/razorpay/verify", done)
        print("verify-payment:", s2, b2[:200])
        s, b = api("/api/stripe/subscription")
        print("VERIFY2:", s, b[:400])
