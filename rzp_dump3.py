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
print("signin:", s)
from camoufox.sync_api import Camoufox
with Camoufox(headless=False, geoip=False) as browser:
    page = browser.new_page()
    page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
    page.context.add_cookies([{"name": k, "value": v, "domain": ".remalt.com", "path": "/"} for k,v in ck.items()])
    page.goto(BASE + "/pricing", timeout=60000, wait_until="domcontentloaded")
    time.sleep(6)
    # check logged-in marker
    print("logged in:", page.locator('button:has-text("Remalt User")').count())
    for attempt in range(3):
        try:
            page.locator('button:has-text("Start Starter trial")').first.click(timeout=10000)
        except Exception as e:
            print("click fail", str(e)[:80])
        # poll for modal
        found = False
        for i in range(20):
            time.sleep(2)
            n = page.locator('button:has-text("Start free trial")').count()
            if n:
                found = True
                print(f"MODAL UP after {(i+1)*2}s")
                break
        if found: break
        print("attempt", attempt, "no modal, retry")
        time.sleep(3)
    time.sleep(3)
    page.screenshot(path=str(HERE / "shots_modal/dump3.png"))
    for f in page.frames:
        print("FRAME:", (f.url or "?")[:100])
        try:
            ins = f.evaluate("""Array.from(document.querySelectorAll('input,select')).map(e=>
              e.tagName+'[name='+(e.name||'')+'][type='+(e.type||'')+'][ph='+(e.placeholder||'')+']')""")
            for x in ins[:30]:
                print("   ", x)
        except Exception as e:
            print("    ERR:", str(e)[:80])
    print("iframes:", page.evaluate("Array.from(document.querySelectorAll('iframe')).map(f=>(f.src||f.id||'?').slice(0,100))"))
