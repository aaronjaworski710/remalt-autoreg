# -*- coding: utf-8 -*-
"""Remalt Card Dashboard — manage cards, check via Stripe, launch trials.
Usage: python card_dashboard.py [port]   (default 8500)
Stdlib only. Data: cards.json (local). STRIPE_PK env for checker.
"""
import json, os, re, subprocess, sys, threading, random, pathlib
import urllib.request, urllib.parse, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = pathlib.Path(__file__).parent
CARDS = HERE / "cards.json"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8500
PK = os.environ.get("STRIPE_PK", "")
if not PK:
    print("WARNING: STRIPE_PK env not set — card checking disabled. Set it to a merchant pk_live_... key.")
LOCK = threading.Lock()
BIN_DEFAULT = "5154620022"


def load():
    if CARDS.exists():
        try:
            return json.load(open(CARDS, encoding="utf-8"))
        except Exception:
            return []
    return []


def save(cards):
    with LOCK:
        json.dump(cards, open(CARDS, "w", encoding="utf-8"), indent=2)


def luhn_ok(num):
    s, a = 0, False
    for ch in reversed(num):
        d = int(ch)
        if a:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        a = not a
    return s % 10 == 0


def luhn_cd(p):
    s, a = 0, False
    for ch in reversed(p):
        d = int(ch)
        if a:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        a = not a
    return str((10 - s % 10) % 10)


def stripe_check(c):
    if not PK:
        return "ERR", "STRIPE_PK env not set"
    data = urllib.parse.urlencode({
        "type": "card", "card[number]": c["number"],
        "card[exp_month]": c["exp"][:2], "card[exp_year]": "20" + c["exp"][2:4],
        "card[cvc]": c["cvv"], "key": PK}).encode()
    r = urllib.request.Request("https://api.stripe.com/v1/payment_methods", data=data,
                               headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            j = json.loads(resp.read().decode())
            return "LIVE", j.get("id", "")[:20]
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode())
            err = j.get("error", {})
            return "DEAD", (err.get("code", "") + ": " + err.get("message", ""))[:60]
        except Exception:
            return "DEAD", "http %s" % e.code
    except Exception as e:
        return "ERR", str(e)[:80]


HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Remalt Cards</title>
<style>
body{background:#0d1117;color:#c9d1d9;font-family:Consolas,monospace;margin:24px}
h1{color:#3fb950;font-size:20px} table{border-collapse:collapse;width:100%;margin:16px 0}
th,td{border:1px solid #30363d;padding:6px 10px;text-align:left;font-size:13px}
th{background:#161b22;color:#58a6ff} tr:hover{background:#161b22}
input,select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px;border-radius:4px;font-family:inherit}
button{background:#238636;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer;font-family:inherit;margin:2px}
button.red{background:#da3633} button.blue{background:#1f6feb}
.live{color:#3fb950;font-weight:bold}.dead{color:#f85149}.unknown{color:#8b949e}
#log{background:#161b22;border:1px solid #30363d;padding:10px;height:160px;overflow-y:auto;font-size:12px;white-space:pre-wrap;margin-top:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}
</style></head><body>
<h1>REMALT CARD DASHBOARD</h1>
<div class="row">
<input id="f_num" placeholder="card number" size="20">
<input id="f_exp" placeholder="MMYY" size="6">
<input id="f_cvv" placeholder="CVV" size="5">
<input id="f_name" placeholder="name" size="18" value="Vlad Reform">
<input id="f_bin" placeholder="BIN for gen" size="12" value="5154620022">
<button onclick="addCard()">+ ADD</button>
<button class="blue" onclick="genBin()">GEN x5</button>
<button class="blue" onclick="checkAll()">CHECK ALL</button>
</div>
<table><thead><tr><th>#</th><th>Number</th><th>Exp</th><th>CVV</th><th>Name</th><th>Status</th><th>Actions</th></tr></thead>
<tbody id="tb"></tbody></table>
<div class="row">
<select id="acc"></select>
<button class="blue" onclick="runTrial()">RUN TRIAL (selected card)</button>
</div>
<div id="log"></div>
<script>
let cards=[], sel=0;
function log(m){const l=document.getElementById('log');l.textContent+=new Date().toLocaleTimeString()+' '+m+'\\n';l.scrollTop=l.scrollHeight}
async function refresh(){const r=await fetch('/api/cards');const d=await r.json();cards=d.cards;render();
 const a=await fetch('/api/accounts');const ad=await a.json();
 const cur=document.getElementById('acc').value;
 document.getElementById('acc').innerHTML=ad.accounts.map(e=>'<option'+(e==cur?' selected':'')+'>'+e+'</option>').join('')}
function render(){document.getElementById('tb').innerHTML=cards.map((c,i)=>
 '<tr'+(i==sel?' style=\"background:#1f6feb22\"':'')+'><td>'+i+'</td><td>'+c.number+'</td><td>'+c.exp+'</td><td>'+c.cvv+'</td><td>'+(c.name||'')+'</td>'+
 '<td class=\"'+(c.status||'unknown').toLowerCase()+'\">'+(c.status||'?')+(c.check_msg?' '+c.check_msg:'')+'</td>'+
 '<td><button class=\"blue\" onclick=\"checkOne('+i+')\">check</button>'+
 '<button onclick=\"selCard('+i+')\">select</button>'+
 '<button class=\"red\" onclick=\"delCard('+i+')\">del</button></td></tr>').join('')}
async function addCard(){const b={number:f_num.value.trim(),exp:f_exp.value.trim(),cvv:f_cvv.value.trim(),name:f_name.value.trim()};
 const r=await fetch('/api/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
 const j=await r.json();log(j.ok?'ADDED '+b.number.slice(-4):'ERR '+j.error);if(j.ok){f_num.value='';f_exp.value='';f_cvv.value=''}refresh()}
async function delCard(i){await fetch('/api/cards/'+i,{method:'DELETE'});log('DELETED #'+i);refresh()}
async function checkOne(i){log('checking #'+i+'...');const r=await fetch('/api/check/'+i,{method:'POST'});const j=await r.json();log('#'+i+' -> '+j.status+' '+j.msg);refresh()}
async function checkAll(){for(let i=0;i<cards.length;i++)await checkOne(i)}
async function genBin(){const r=await fetch('/api/gen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bin:f_bin.value.trim()})});const j=await r.json();log('GEN added '+j.added);refresh()}
function selCard(i){sel=i;render();log('card #'+i+' selected')}
async function runTrial(){const em=document.getElementById('acc').value;log('TRIAL card#'+sel+' acc='+em+' -> trial.log');
 const r=await fetch('/api/trial',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idx:sel,email:em})});const j=await r.json();log(j.ok?'trial launched pid='+j.pid:'ERR '+j.error)}
refresh();setInterval(refresh,15000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/api/cards":
            self._send(200, {"cards": load()})
        elif self.path == "/api/accounts":
            accs = []
            f = HERE / "accounts.jsonl"
            if f.exists():
                for l in f.read_text(encoding="utf-8").splitlines():
                    try:
                        accs.append(json.loads(l)["email"])
                    except Exception:
                        pass
            self._send(200, {"accounts": accs})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(ln) or b"{}") if ln else {}
        if self.path == "/api/cards":
            num = re.sub(r"\D", "", body.get("number", ""))
            exp = re.sub(r"\D", "", body.get("exp", ""))
            cvv = re.sub(r"\D", "", body.get("cvv", ""))
            if len(num) < 15 or not luhn_ok(num):
                return self._send(400, {"ok": False, "error": "bad luhn/length"})
            if len(exp) != 4 or len(cvv) < 3:
                return self._send(400, {"ok": False, "error": "bad exp/cvv"})
            cards = load()
            cards.append({"number": num, "exp": exp, "cvv": cvv,
                          "name": body.get("name") or "Vlad Reform", "status": ""})
            save(cards)
            self._send(200, {"ok": True, "idx": len(cards) - 1})
        elif self.path.startswith("/api/check/"):
            i = int(self.path.rsplit("/", 1)[1])
            cards = load()
            if i >= len(cards):
                return self._send(400, {"ok": False, "error": "no card"})
            st, msg = stripe_check(cards[i])
            cards[i]["status"] = st
            cards[i]["check_msg"] = msg
            save(cards)
            self._send(200, {"status": st, "msg": msg})
        elif self.path == "/api/gen":
            BIN = re.sub(r"\D", "", body.get("bin") or BIN_DEFAULT) or BIN_DEFAULT
            if len(BIN) > 15:
                return self._send(400, {"ok": False, "error": "bin too long"})
            cards = load()
            have = {c["number"] for c in cards}
            added = 0
            guard = 0
            while added < 5 and guard < 500:
                guard += 1
                b = BIN + "".join(str(random.randint(0, 9)) for _ in range(15 - len(BIN)))
                n = b + luhn_cd(b)
                if n in have:
                    continue
                cards.append({"number": n,
                              "exp": random.choice(["1128", "1229", "1030", "0530"]),
                              "cvv": "%03d" % random.randint(0, 999),
                              "name": "Vlad Reform", "status": ""})
                have.add(n)
                added += 1
            save(cards)
            self._send(200, {"ok": True, "added": added})
        elif self.path == "/api/trial":
            idx, email = body.get("idx", 0), body.get("email", "")
            if not email:
                return self._send(400, {"ok": False, "error": "no email"})
            py = sys.executable
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            logf = open(HERE / "trial.log", "ab")
            p = subprocess.Popen(
                [py, "-X", "utf8", "-u", str(HERE / "remalt_trial.py"), str(idx), email],
                stdout=logf, stderr=logf, env=env, cwd=str(HERE))
            self._send(200, {"ok": True, "pid": p.pid})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_DELETE(self):
        if self.path.startswith("/api/cards/"):
            i = int(self.path.rsplit("/", 1)[1])
            cards = load()
            if i < len(cards):
                cards.pop(i)
                save(cards)
                self._send(200, {"ok": True})
            else:
                self._send(400, {"ok": False})
        else:
            self._send(404, {"ok": False})


if __name__ == "__main__":
    print("Card dashboard: http://127.0.0.1:%d" % PORT)
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
