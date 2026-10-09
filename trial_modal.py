# -*- coding: utf-8 -*-
"""Fill embedded Stripe trial modal on remalt.com/pricing (same-origin, no PX)."""
import json, time, pathlib, sys, urllib.request, http.cookiejar
BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
SHOTS = HERE / "shots_modal"
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
    print("TRIAL MODAL OPEN")
    time.sleep(5)
    page.screenshot(path=str(SHOTS / "01_modal.png"))
    # Stripe Payment Element renders inside iframe even when embedded
    fr = None
    for f in page.frames:
        u = f.url or ""
        if "stripe.com" in u or u in ("about:blank", ""):
            try:
                if f.locator('input[name="cardNumber"]').count() > 0 or "stripe" in u:
                    fr = f
                    break
            except Exception:
                if "stripe" in u:
                    fr = f
                    break
    if fr is None:
        for f in page.frames:
            if f is not page.main_frame:
                fr = f
                break
    target = fr if fr else page.main_frame
    print("frame:", (fr.url[:80] if fr else "MAIN"))
    def ffill(sel, val, t=6000):
        try:
            loc = target.locator(sel).first
            loc.wait_for(state="visible", timeout=t)
            loc.fill(val)
            print("OK", sel)
            return True
        except Exception as e:
            print("miss", sel, str(e)[:60])
            return False
    ffill('input[name="cardNumber"]', card["number"])
    ffill('input[name="cardExpiry"]', card["exp"][:2] + card["exp"][2:])
    ffill('input[name="cardCvc"]', card["cvv"])
    # dump ALL inputs in ALL frames for visibility
    for f in page.frames:
        try:
            ins = f.evaluate("Array.from(document.querySelectorAll('input,select')).map(e=>e.tagName+'['+(e.name||e.type)+']|'+(e.placeholder||''))")
            if ins: print("FRAME", (f.url or "?")[:60], ins)
        except Exception:
            pass
    def pfill(sel, val):
        # try iframe first, then page
        for t in ([target, page] if target is not page else [page]):
            try:
                loc = t.locator(sel).first
                loc.wait_for(state="visible", timeout=4000)
                loc.fill(val)
                print("OK", sel)
                return True
            except Exception:
                continue
        print("miss", sel)
        return False
    pfill('input[name="name"]', card["name"])
    try:
        page.select_option('select[name="billingCountry"]', "US")
        print("OK country")
    except Exception:
        try:
            target.select_option('select[name="billingCountry"]', "US")
            print("OK country(iframe)")
        except Exception:
            print("country skip")
    pfill('input[name="addressLine1"]', "1234 Main St")
    pfill('input[name="locality"]', "New York")
    pfill('input[name="postalCode"]', "10001")
    time.sleep(1)
    page.screenshot(path=str(SHOTS / "02_filled.png"))
    try:
        page.locator('button:has-text("Start free trial")').first.click(timeout=8000)
        print("SUBMIT CLICKED")
    except Exception as e:
        print("submit fail", str(e)[:100])
    result = "TIMEOUT"
    for i in range(30):
        time.sleep(3)
        if i % 3 == 0:
            page.screenshot(path=str(SHOTS / f"03_w{i:02d}.png"))
            try: body = page.locator("body").inner_text()[:200].replace("\n"," | ")
            except Exception: body = "?"
            print(f"[{i*3}s]", body)
        try: low = page.locator("body").inner_text().lower()
        except Exception: low = ""
        if "welcome" in low or "you're all set" in low or "trial started" in low or "success" in low:
            result = "SUCCESS"; print(">>> SUCCESS"); break
        if "declined" in low or "could not be processed" in low or "invalid" in low:
            result = "DECLINED"; print(">>> DECLINED:", low[:300]); break
    page.screenshot(path=str(SHOTS / "04_final.png"))
    json.dump({"result": result, "url": page.url}, open(HERE / "modal_result.json", "w"))
    print("RESULT:", result, "url:", page.url)
s,b = api("/api/stripe/subscription")
print("VERIFY:", s, b[:400])
