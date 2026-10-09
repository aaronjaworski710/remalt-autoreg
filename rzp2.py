# -*- coding: utf-8 -*-
"""Try via real page UI: find trial button on /pricing, or inject checkout.js properly."""
import json, time, pathlib, sys, urllib.request, http.cookiejar
BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
a = accs[-1]
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

from camoufox.sync_api import Camoufox
with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
    page.context.add_cookies([{"name": k, "value": v, "domain": ".remalt.com", "path": "/"} for k,v in ck.items()])
    page.goto(BASE + "/pricing", timeout=60000, wait_until="domcontentloaded")
    time.sleep(6)
    # dump buttons/links
    els = page.evaluate("""() => Array.from(document.querySelectorAll('button, a')).map(e =>
        (e.tagName+':'+(e.innerText||'').trim().slice(0,60)+'|href='+(e.getAttribute('href')||'').slice(0,80))).filter(x=>x.length>4)""")
    for e in els: print(e)
    # also check if Razorpay global exists
    print("Razorpay global:", page.evaluate("() => typeof window.Razorpay"))
