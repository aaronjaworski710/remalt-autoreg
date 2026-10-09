# -*- coding: utf-8 -*-
import tempfile, json, sys, time, pathlib
from camoufox.sync_api import Camoufox

T = pathlib.Path(tempfile.gettempdir())
url = open(T / "remalt_checkout_url.txt").read().strip()
card = json.load(open(pathlib.Path(__file__).parent / "cards.json"))

shots = pathlib.Path(__file__).parent / "shots"
shots.mkdir(exist_ok=True)

with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(url, timeout=60000, wait_until="domcontentloaded")
    time.sleep(8)
    print("TITLE:", page.title())
    page.screenshot(path=str(shots / "01_loaded.png"))

    # find card frame or direct inputs
    def find_inputs():
        frames = [page] + list(page.frames)
        for f in frames:
            try:
                if f.locator('input[name="cardNumber"]').count() > 0:
                    return f
            except Exception:
                pass
        return None

    f = None
    for i in range(12):
        f = find_inputs()
        if f: break
        time.sleep(3)
    if not f:
        print("NO CARD FORM"); page.screenshot(path=str(shots/"02_noform.png")); sys.exit(2)
    print("FORM FRAME OK")

    def fill(name, val):
        try:
            loc = f.locator(f'input[name="{name}"]')
            loc.focus(timeout=5000)
        except Exception:
            f.evaluate(f'''(v) => {{ const el = document.querySelector('input[name="{name}"]'); el && el.focus(); }}''', val)
        loc = f.locator(f'input[name="{name}"]')
        loc.press_sequentially(val, delay=70)
        time.sleep(0.4)
        print(name, "=", loc.input_value())

    fill("cardNumber", card["number"])
    fill("cardExpiry", card["exp"])
    fill("cardCvc", card["cvc"])
    # name on card
    try:
        if f.locator('input[name="name"]').count() > 0:
            fill("name", card.get("name", "VLAD REFORM"))
    except Exception: pass
    # billing fields (country UA etc) — fill if present
    for nm, val in [("billingName", card.get("name","VLAD REFORM")), ("billingAddressLine1","Khreshchatyk St 1"),
                    ("billingLocality","Kyiv"), ("billingPostalCode","01001"), ("billingAdministrativeArea","Kyiv")]:
        try:
            if f.locator(f'input[name="{nm}"]').count() > 0:
                fill(nm, val)
        except Exception: pass
    page.screenshot(path=str(shots/"03_filled.png"))

    # submit
    submitted = False
    for sel in ['button[type="submit"]', '#submit', 'div[role="button"]']:
        try:
            btn = f.locator(sel).first
            if btn.count() > 0:
                time.sleep(1)
                if btn.is_disabled():
                    print("btn disabled, wait"); time.sleep(3)
                btn.click(timeout=8000, force=True)
                submitted = True
                print("CLICKED", sel)
                break
        except Exception as e:
            continue
    if not submitted:
        f.evaluate('document.querySelector(\'button[type="submit"]\')?.click()')
        print("JS CLICK")

    # wait for result / 3DS
    for i in range(40):
        time.sleep(3)
        t = page.title()
        body = page.locator("body").inner_text()[:400].replace("\n", " ")
        if i % 4 == 0:
            print(f"[{i*3}s] title={t!r}")
            print("   body:", body[:300])
        page.screenshot(path=str(shots/f"04_wait_{i:02d}.png"))
        low = body.lower()
        if "3d secure" in low or "verification" in low or "3ds" in low or "підтверд" in low or "подтверд" in low or "one-time" in low or "password from your bank" in low:
            print("3DS DETECTED — need Vlad phone"); page.screenshot(path=str(shots/"3ds.png")); 
            open(T/"remalt_hit_state.json","w").write(json.dumps({"state":"3ds","title":t,"body":body}))
            sys.exit(3)
        if "success" in low or "thank you" in low or "paid" in low or "subscription" in low or page.url != url and "stripe" not in page.url:
            print("DONE?", t, page.url)
            open(T/"remalt_hit_state.json","w").write(json.dumps({"state":"maybe_done","title":t,"url":page.url,"body":body}))
            break
        if "declined" in low or "incorrect" in low or "invalid" in low or "failed" in low or "not allowed" in low or "connection issues" in low:
            print("FAIL SIGNAL:", body)
            open(T/"remalt_hit_state.json","w").write(json.dumps({"state":"fail","title":t,"body":body}))
            break
    else:
        open(T/"remalt_hit_state.json","w").write(json.dumps({"state":"timeout","title":page.title(),"url":page.url}))
    page.screenshot(path=str(shots/"05_final.png"))
    print("FINAL:", page.title(), page.url)
