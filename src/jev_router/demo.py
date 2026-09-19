from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .config import AppConfig
from .models import Task
from .pricing import estimate_request_cost, estimate_tokens
from .routers import rule_router


PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jev Router — ölçüm konsolu</title>
<style>
:root{--paper:#eef4f7;--ink:#13233f;--muted:#607087;--cyan:#1e9fb2;--copper:#d86642;--mint:#ccebe3;--line:#b9cad4}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,-apple-system,sans-serif;min-height:100vh}
main{width:min(980px,calc(100% - 32px));margin:0 auto;padding:54px 0 70px}.eyebrow{font:700 12px ui-monospace,monospace;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan)}
h1{font:500 clamp(42px,8vw,86px)/.92 Georgia,serif;letter-spacing:-.055em;margin:18px 0 20px;max-width:820px}.intro{max-width:650px;color:var(--muted);font-size:18px;line-height:1.55}
.grid{display:grid;grid-template-columns:1.25fr .75fr;gap:18px;margin-top:42px}.panel{background:#fff;border:1px solid var(--line);padding:28px;box-shadow:7px 7px 0 #d7e3e9}.panel h2{font:600 18px Georgia,serif;margin:0 0 18px}
label{display:block;font:700 11px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;margin-bottom:9px}textarea{width:100%;min-height:170px;border:1px solid #94a9b6;background:#f9fcfd;color:var(--ink);padding:15px;font:15px/1.55 system-ui;resize:vertical}textarea:focus,button:focus{outline:3px solid #8dd4dd;outline-offset:2px}
button{border:0;background:var(--ink);color:white;font:700 13px ui-monospace,monospace;padding:13px 17px;margin-top:14px;cursor:pointer}button:hover{background:var(--cyan)}.rail{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;margin:28px 0 18px}.rail i{height:2px;background:var(--line)}.rail b{border:2px solid var(--cyan);border-radius:50%;width:54px;height:54px;display:grid;place-items:center;font:700 11px ui-monospace,monospace;background:var(--paper)}
.result{display:none}.result.ready{display:block}.model{font:600 27px Georgia,serif;color:var(--copper);overflow-wrap:anywhere}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}.stat{background:var(--mint);padding:12px}.stat span{display:block;font:700 10px ui-monospace,monospace;text-transform:uppercase;color:var(--muted)}.stat strong{font:600 18px ui-monospace,monospace}.note{font-size:12px;color:var(--muted);line-height:1.45;margin-top:15px}
@media(max-width:720px){main{padding-top:34px}.grid{grid-template-columns:1fr}.panel{padding:21px}.stats{grid-template-columns:1fr}}
@media(prefers-reduced-motion:no-preference){.panel{animation:arrive .45s ease both}.panel:nth-child(2){animation-delay:.08s}@keyframes arrive{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}}
</style></head><body><main><div class="eyebrow">ErenAILab / pre-routing laboratuvarı</div><h1>Yanıtı yazmadan önce doğru hattı seç.</h1><p class="intro">Bu yerel demo isteğin içeriğini yeniden göstermez veya kaydetmez. Çevrimdışı kural politikası seçimi, süreyi ve sabit fiyat tablosundan tahmini bedeli gösterir.</p>
<div class="grid"><section class="panel"><h2>Bir metin görevi gir</h2><form id="route-form"><label for="prompt">İstek</label><textarea id="prompt" name="prompt" required placeholder="Örn. Bu müşteri mesajını üç etiketten biriyle sınıflandır…"></textarea><button type="submit">Rotayı ölç</button></form></section>
<section class="panel"><h2>Seçilen hat</h2><div class="rail"><i></i><b>ROUTE</b><i></i></div><div id="empty" class="note">İstek gönderildiğinde yalnızca karar ve ölçüm burada görünür.</div><div id="result" class="result"><div id="model" class="model"></div><div class="stats"><div class="stat"><span>Yönlendirme</span><strong id="latency"></strong></div><div class="stat"><span>Tahmini USD</span><strong id="cost"></strong></div><div class="stat"><span>Girdi tokenı</span><strong id="tokens"></strong></div><div class="stat"><span>Kural</span><strong id="rule"></strong></div></div><p class="note">Bu çevrimdışı ekranda model çağrısı yapılmaz. Bedel gerçek usage veya fatura değildir.</p></div></section></div></main>
<script>document.getElementById('route-form').addEventListener('submit',async(e)=>{e.preventDefault();const p=document.getElementById('prompt').value;const r=await fetch('/route',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:new URLSearchParams({prompt:p})});const d=await r.json();document.getElementById('empty').style.display='none';document.getElementById('result').classList.add('ready');for(const k of ['model','latency','cost','tokens','rule'])document.getElementById(k).textContent=d[k];document.getElementById('prompt').value='';});</script></body></html>"""


def handler_factory(config: AppConfig):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            # Avoid logging paths, queries, or private prompt content.
            return

        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/route":
                self.send_error(404)
                return
            length = min(int(self.headers.get("Content-Length", "0")), 100_000)
            prompt = parse_qs(self.rfile.read(length).decode()).get("prompt", [""])[0]
            started = time.perf_counter()
            task = Task("demo", "demo", "unknown", "unknown", prompt, "contains_all", [], {"modality": "text"}, {}, {})
            decision = rule_router(task, config)
            elapsed = (time.perf_counter() - started) * 1000
            role = decision.selected or "strong"
            model = getattr(config, role)
            cost = estimate_request_cost(prompt, 128, model)
            payload = {
                "model": model.model_id,
                "latency": f"{elapsed:.2f} ms",
                "cost": f"${cost:.6f}",
                "tokens": str(estimate_tokens(prompt)),
                "rule": decision.rule.replace("rule_pattern_", ""),
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(config: AppConfig, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), handler_factory(config))
    print(f"Demo: http://{host}:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDemo stopped.")
    finally:
        server.server_close()
