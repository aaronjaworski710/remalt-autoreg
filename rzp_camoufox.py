# -*- coding: utf-8 -*-
"""Razorpay starter_promo hit via camoufox on remalt.com origin (same-origin verify)."""
import tempfile, json, time, pathlib, sys
from camoufox.sync_api import Camoufox

T = pathlib.Path(tempfile.gettempdir())
SHOTS = pathlib.Path(__file__).parent / "shots_rzp"; SHOTS.mkdir(exist_ok=True)
order = json.load(open(T/"remalt_rzp_order.json"))
card = json.load(open(pathlib.Path(__file__).parent / "cards.json"))

JS_SETUP = """
(cfg) => {
  window.__rzpLog = [];
  const L = s => window.__rzpLog.push(String(s));
  const sc = document.createElement('script');
  sc.src = 'https://checkout.razorpay.com/v1/checkout.js';
  sc.onerror = () => L('SCRIPT_LOAD_ERR');
  document.head.appendChild(sc);
  let tries = 0;
  const iv = setInterval(() => {
    tries++;
    if (typeof Razorpay !== 'undefined') { clearInterval(iv); L('RAZORPAY_DEFINED'); }
    else if (tries > 25) { clearInterval(iv); L('RAZORPAY_TIMEOUT'); }
  }, 400);
  window.__mk = function(){
    if (typeof Razorpay === 'undefined') { L('STILL_UNDEFINED'); return; }
    try {
      window.__rzp = new Razorpay({
        key: cfg.key,
        subscription_id: cfg.subscriptionId,
        name: 'Remalt',
        description: cfg.description,
        currency: 'INR',
        prefill: {email: cfg.prefill.email, name: cfg.prefill.name},
        theme: {color: '#072c1f'},
        handler: function(resp){
          L('HANDLER '+JSON.stringify(resp));
          fetch('https://remalt.com/api/razorpay/verify', {
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(resp)
          }).then(r=>r.text()).then(t=>L('VERIFY '+t)).catch(e=>L('VERR '+e));
        },
        modal: {ondismiss: () => L('DISMISSED')}
      });
      window.__rzp.on('payment.failed', resp => L('FAILED '+JSON.stringify(resp.error)));
      L('READY');
    } catch(e){ L('SETUP_ERR '+e); }
  };
  window.pay = () => { window.__rzp.open(); L('OPENED'); };
}
"""

with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    # login with session cookie: set better_auth cookie via sign-in from browser fetch
    page.goto("https://remalt.com/auth/signin", timeout=60000, wait_until="domcontentloaded")
    acc = json.loads(open(pathlib.Path(__file__).parent / "accounts.jsonl", encoding="utf-8").readlines()[-1])
    signin = page.evaluate("""async (a) => {
        const r = await fetch('/api/auth/sign-in/email', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(a)});
        return (await r.text()).slice(0,150);
    }""", {"email": acc["email"], "password": acc["password"]})
    print("signin:", signin)
    time.sleep(3)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    time.sleep(2)
    page.evaluate(JS_SETUP, order)
    for _ in range(30):
        log = page.evaluate("window.__rzpLog")
        if any(x in log for x in ("RAZORPAY_DEFINED","RAZORPAY_TIMEOUT","SCRIPT_LOAD_ERR")): break
        time.sleep(1)
    print("load log:", page.evaluate("window.__rzpLog"))
    page.evaluate("window.__mk()")
    for _ in range(15):
        log = page.evaluate("window.__rzpLog")
        if "READY" in log or "SETUP_ERR" in log or "STILL_UNDEFINED" in log: break
        time.sleep(1)
    print("setup log:", page.evaluate("window.__rzpLog"))
    page.evaluate("window.pay()")
    time.sleep(6)
    page.screenshot(path=str(SHOTS/"01_modal.png"))
    print("frames:", [f.url[:80] for f in page.frames])
    # find razorpay modal frame
    rzf = None
    for f in page.frames:
        if "razorpay" in f.url or f.locator('input[name="card[number]"], input[autocomplete="cc-number"], input[name="contact"], input[placeholder*="Card"]').count() > 0:
            rzf = f; break
    if rzf is None: rzf = page
    print("rzp frame:", rzf.url[:100])
    # dump input names
    names = rzf.evaluate("Array.from(document.querySelectorAll('input')).map(i=>i.name+'|'+i.placeholder+'|'+i.autocomplete)")
    print("inputs:", names)
    json.dump({"frames":[f.url for f in page.frames], "inputs":names}, open(T/"rzp_state.json","w"))
    page.screenshot(path=str(SHOTS/"02_inputs.png"))
    # save page object refs can't persist -> fill now
    def fill(selname, val):
        for sel in selname:
            try:
                loc = rzf.locator(sel).first
                if loc.count() > 0:
                    loc.focus(timeout=4000)
                    loc.press_sequentially(val, delay=60)
                    time.sleep(0.3)
                    print("filled", sel, "->", loc.input_value())
                    return True
            except Exception as e:
                continue
        print("MISS", selname)
        return False
    fill(['input[name="card[number]"]','input[autocomplete="cc-number"]','input[placeholder*="Card number" i]','input[name="card_number"]'], card["number"])
    exp = card["exp"]; fill(['input[name="card[expiry]"]','input[autocomplete="cc-exp"]','input[placeholder*="MM" i]','input[name="expiry"]'], exp[:2]+exp[2:])
    fill(['input[name="card[cvv]"]','input[autocomplete="cc-csc"]','input[placeholder*="CVV" i]','input[name="cvv"]'], card["cvc"])
    fill(['input[name="card[name]"]','input[autocomplete="cc-name"]','input[placeholder*="Name" i]'], card["name"])
    time.sleep(1)
    page.screenshot(path=str(SHOTS/"03_filled.png"))
    # OTP may be needed for 3DS; click pay button
    try:
        btn = rzf.locator('button:has-text("Pay"), button:has-text("Make Payment"), button[type="submit"]').first
        btn.click(timeout=6000)
        print("PAY CLICKED")
    except Exception as e:
        rzf.evaluate("document.querySelectorAll('button').forEach(b=>{if(/pay|submit/i.test(b.textContent+b.type))b.click()})")
        print("JS PAY CLICK")
    # watch log + OTP modal
    for i in range(60):
        time.sleep(3)
        log = page.evaluate("window.__rzpLog")
        if i % 3 == 0:
            print(f"[{i*3}s]", log[-3:] if log else [])
            page.screenshot(path=str(SHOTS/f"04_w{i:02d}.png"))
        joined = " ".join(log)
        if "VERIFY" in joined or "HANDLER" in joined:
            print("PAYMENT OK:", joined); break
        if "FAILED" in joined or "DISMISSED" in joined:
            print("FAIL:", joined); break
        # OTP screen?
        txt = page.locator("body").inner_text().lower()
        if "otp" in txt or "one time" in txt or "password from" in txt:
            print("OTP/3DS SCREEN"); page.screenshot(path=str(SHOTS/"otp.png"))
            open(T/"rzp_state.json","w").write(json.dumps({"state":"otp","log":log}))
            sys.exit(3)
    else:
        print("TIMEOUT", page.evaluate("window.__rzpLog"))
    page.screenshot(path=str(SHOTS/"05_final.png"))
    open(T/"rzp_final.json","w").write(json.dumps(page.evaluate("window.__rzpLog")))
