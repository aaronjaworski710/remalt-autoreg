import json, time, pathlib, sys, urllib.request, http.cookiejar
BASE = "https://remalt.com"
HERE = pathlib.Path(__file__).parent
accs = [json.loads(l) for l in open(HERE / "accounts.jsonl", encoding="utf-8") if l.strip()]
a = accs[-2] if len(accs) > 1 else accs[-1]  # другой акк
print("acc:", a["email"])
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
    time.sleep(8)
    print("user button:", page.locator('button:has-text("Remalt User")').count())
    print("trial buttons:", page.locator('button:has-text("Start Starter trial")').count())
    btns = page.evaluate("Array.from(document.querySelectorAll('button')).map(b=>b.innerText.trim()).filter(x=>x)")
    print("ALL BUTTONS:", btns)
    page.screenshot(path=str(HERE / "shots_modal/check.png"))
    try:
        page.locator('button:has-text("Start Starter trial")').first.click(timeout=10000)
        print("CLICKED")
    except Exception as e:
        print("click err:", str(e)[:150])
    time.sleep(8)
    page.screenshot(path=str(HERE / "shots_modal/check2.png"))
    print("free trial btn:", page.locator('button:has-text("Start free trial")').count())
    print("modal text:", page.locator('[role="dialog"]').count())
    try:
        d = page.locator('[role="dialog"]').first.inner_text()[:200]
        print("dialog:", d.replace("\n"," | "))
    except Exception as e:
        print("no dialog:", str(e)[:80])
