# -*- coding: utf-8 -*-
"""Remalt trial activator v2 — embedded Stripe Elements modal on /pricing.
Card -> js.stripe.com elements-inner-payment frame (name=number/expiry/cvc)
Address -> elements-inner-address frame (name/country/addressLine1/locality/postalCode)
Usage: python remalt_trial2.py [card_index] [email]
"""
import json, time, pathlib, sys, urllib.request, http.cookiejar

BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
SHOTS = HERE / "shots_modal"
SHOTS.mkdir(exist_ok=True)

accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
cards = json.load(open(HERE / "cards.json", encoding="utf-8"))
ci = int(sys.argv[1]) if len(sys.argv) > 1 else 0
email = sys.argv[2] if len(sys.argv) > 2 else None
a = next((x for x in accs if x["email"] == email), accs[-2] if len(accs) > 1 else accs[-1])
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
ck = {c.name: c.value for c in cj}
print("signin:", s)

from camoufox.sync_api import Camoufox

result = "TIMEOUT"
with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
    page.context.add_cookies([{"name": k, "value": v, "domain": ".remalt.com", "path": "/"}
                              for k, v in ck.items()])
    page.goto(BASE + "/pricing", timeout=60000, wait_until="domcontentloaded")
    time.sleep(6)

    # open modal with retries (dialog detection + longer waits)
    modal = False
    for attempt in range(5):
        time.sleep(4 + attempt * 3)
        try:
            btn = page.locator('button:has-text("Start Starter trial")').first
            btn.scroll_into_view_if_needed(timeout=5000)
            btn.click(timeout=10000, force=True)
            print("clicked attempt", attempt)
        except Exception as e:
            print("click err", str(e)[:80])
        for i in range(12):
            time.sleep(2)
            n = page.locator('button:has-text("Start free trial")').count()
            d = page.locator('[role="dialog"]').count()
            if n and d:
                modal = True
                break
        if modal:
            break
    if not modal:
        print("MODAL NOT UP")
        page.screenshot(path=str(SHOTS / "no_modal.png"))
        sys.exit(2)
    print("MODAL UP")
    time.sleep(3)

    # locate stripe element frames
    pay_fr = addr_fr = None
    for f in page.frames:
        u = f.url or ""
        if "elements-inner-payment" in u:
            pay_fr = f
        elif "elements-inner-address" in u:
            addr_fr = f
    print("pay frame:", bool(pay_fr), "addr frame:", bool(addr_fr))
    if not pay_fr:
        sys.exit(3)

    # wait inputs visible
    pay_fr.locator('input[name="number"]').wait_for(state="visible", timeout=15000)

    def ffill(fr, sel, val, delay=50):
        loc = fr.locator(sel).first
        loc.wait_for(state="visible", timeout=10000)
        try:
            loc.fill(val, timeout=8000)
        except Exception:
            try:
                loc.click(force=True, timeout=5000)
            except Exception:
                loc.evaluate("e => e.focus()")
            loc.press_sequentially(val, delay=delay)
        print("OK", sel, "->", val[:6] + ("..." if len(val) > 6 else ""))

    ffill(pay_fr, 'input[name="number"]', card["number"], 60)
    ffill(pay_fr, 'input[name="expiry"]', card["exp"][:2] + card["exp"][2:], 60)
    ffill(pay_fr, 'input[name="cvc"]', card["cvv"], 60)
    if addr_fr:
        try:
            ffill(addr_fr, 'input[name="name"]', card["name"], 30)
            addr_fr.select_option('select[name="country"]', "US")
            print("OK country US")
            ffill(addr_fr, 'input[name="addressLine1"]', "1234 Main St", 30)
            ffill(addr_fr, 'input[name="locality"]', "New York", 30)
            try:
                addr_fr.select_option('select[name="administrativeArea"]', "NY")
                print("OK state NY")
            except Exception:
                print("state skip")
            ffill(addr_fr, 'input[name="postalCode"]', "10001", 30)
        except Exception as e:
            print("addr partial:", str(e)[:120])
    time.sleep(2)
    page.screenshot(path=str(SHOTS / "filled2.png"))

    page.locator('button:has-text("Start free trial")').first.click(timeout=10000)
    print("SUBMIT CLICKED")

    # hcaptcha checkbox gate: click by absolute mouse coords (nested iframe defeats locator.click)
    def try_hcaptcha():
        # find visible hcaptcha iframe element in DOM -> bounding box -> click checkbox zone
        boxes = page.evaluate("""() => {
            const out = [];
            for (const f of document.querySelectorAll('iframe')) {
                const r = f.getBoundingClientRect();
                if (r.width > 50 && r.height > 30) out.push({src:(f.src||'').slice(0,120), x:r.x, y:r.y, w:r.width, h:r.height});
            }
            return out;
        }""")
        for bx in boxes:
            if "hcaptcha" in bx["src"] or "challenge" in bx["src"]:
                # checkbox sits at ~left 30px, vertical center
                page.mouse.click(bx["x"] + 32, bx["y"] + bx["h"] / 2)
                print("HCAPTCHA MOUSE CLICK at", round(bx["x"] + 32), round(bx["y"] + bx["h"] / 2), bx["src"][:60])
                time.sleep(4)
                # also try locator fallbacks inside frames
                for f in page.frames:
                    fu = (f.url or "").lower()
                    if "hcaptcha" in fu:
                        for sel in ('#checkbox', 'div[role="checkbox"]', 'label:has-text("I am human")'):
                            try:
                                cb = f.locator(sel).first
                                if cb.count() > 0 and cb.is_visible():
                                    cb.click(timeout=2500, force=True)
                                    print("HCAPTCHA LOC CLICK:", sel)
                            except Exception:
                                pass
                return True
        return False

    for rnd in range(8):
        time.sleep(5)
        if try_hcaptcha():
            time.sleep(8)
        # success check after captcha
        try:
            low = page.locator("body").inner_text().lower()
        except Exception:
            low = ""
        if "error occurred while processing your card" in low:
            print(">>> CARD ERROR shown")
            break
        if not page.locator('button:has-text("Start free trial")').count():
            print(">>> modal gone after captcha round", rnd)
            break

    for i in range(50):
        time.sleep(3)
        if i % 4 == 0:
            page.screenshot(path=str(SHOTS / f"w{i:02d}.png"))
        try:
            low = page.locator("body").inner_text().lower()
        except Exception:
            low = ""
        url = page.url
        # 3DS/OTP
        otp_fr = None
        for f in page.frames:
            fu = (f.url or "").lower()
            if "3ds" in fu or "acs" in fu or "mpi" in fu or "auth" in fu and "stripe" not in fu:
                otp_fr = f
        if otp_fr is not None:
            result = "3DS"
            print(">>> 3DS/ACS frame:", otp_fr.url[:100])
            page.screenshot(path=str(SHOTS / "3ds.png"))
            try:
                t = otp_fr.locator("body").inner_text()[:400]
                print("3DS TEXT:", t.replace("\n", " | "))
            except Exception:
                pass
            break
        if any(w in low for w in ("welcome", "trial started", "you're all set", "success", "redirecting")):
            result = "SUCCESS"
            print(">>> SUCCESS text:", low[:250])
            break
        if any(w in low for w in ("declined", "could not be processed", "your card was declined", "payment failed", "invalid")):
            result = "DECLINED"
            print(">>> DECLINED:", low[:350])
            page.screenshot(path=str(SHOTS / "declined.png"))
            break
        if not page.locator('button:has-text("Start free trial")').count() and url.startswith(BASE):
            # modal closed on its own -> probably success redirect in-app
            time.sleep(4)
            low2 = page.locator("body").inner_text().lower()
            if "pricing" not in url and ("dashboard" in url or "welcome" in low2):
                result = "SUCCESS"
                print(">>> modal closed, now at:", url)
            else:
                print(f"[{i*3}s] modal closed? url={url[:80]} body={low2[:100]}")
        else:
            if i % 4 == 0:
                print(f"[{i*3}s] url={url[:80]} body={low[:80].replace(chr(10),' ')}")
    page.screenshot(path=str(SHOTS / "final2.png"))
    print("RESULT:", result)
    json.dump({"result": result, "url": page.url, "acc": a["email"], "card_idx": ci},
              open(HERE / "trial_result.json", "w"))

time.sleep(5)
s, b = api("/api/stripe/subscription")
print("VERIFY:", s, b[:400])
if '"plan":"starter"' in b or '"access":"starter"' in b:
    print("=== TRIAL ACTIVE ===")
