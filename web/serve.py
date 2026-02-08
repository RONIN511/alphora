"""
AgentChat Frontend Server (with reverse proxy for remote APIs)

    python serve.py                                         # localhost:8818
    python serve.py --api http://192.168.1.100:8000         # proxy remote API
    python serve.py --port 3000 --no-browser

When --api is set, /api/* requests are proxied to the remote backend,
solving CORS issues. Set frontend endpoint to /api/v1/chat/completions.
"""
import argparse, http.server, json, socketserver, sys, threading, webbrowser
from functools import partial
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DIR = Path(__file__).parent.resolve()

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, api_base=None, **kw):
        self.api_base = api_base.rstrip('/') if api_base else None
        super().__init__(*a, directory=str(DIR), **kw)

    def do_GET(self):
        if self.path in ('/', ''): self.path = '/index.html'
        if self.path == '/index.html' and self.api_base:
            c = (DIR / 'index.html').read_text('utf-8')
            c = c.replace('</head>', "<script>addEventListener('DOMContentLoaded',function(){var e=document.getElementById('cfgUrl');if(e)e.value='/api/v1/chat/completions'})</script></head>")
            b = c.encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','text/html;charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/') and self.api_base:
            self._proxy()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def _proxy(self):
        target = self.api_base + self.path[4:]
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else None
        is_stream = False
        if body:
            try: is_stream = json.loads(body).get('stream', False)
            except: pass
        fwd = {}
        for h in ('Content-Type','Authorization','Accept'):
            v = self.headers.get(h)
            if v: fwd[h] = v
        try:
            req = Request(target, data=body, headers=fwd, method='POST')
            resp = urlopen(req, timeout=120)
            self.send_response(resp.status)
            for k,v in resp.getheaders():
                if k.lower() not in ('transfer-encoding','connection','content-encoding'):
                    self.send_header(k, v)
            self._cors()
            if is_stream:
                self.send_header('Content-Type','text/event-stream')
                self.send_header('Cache-Control','no-cache')
                self.send_header('X-Accel-Buffering','no')
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk: break
                    self.wfile.write(chunk); self.wfile.flush()
            else:
                data = resp.read()
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        except HTTPError as e:
            b = e.read(); self.send_response(e.code); self._cors()
            self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
        except URLError as e:
            m = json.dumps({"error":f"Proxy: {e.reason}"}).encode()
            self.send_response(502); self._cors(); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(m))); self.end_headers(); self.wfile.write(m)
        except Exception as e:
            m = json.dumps({"error":str(e)}).encode()
            self.send_response(500); self._cors(); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(m))); self.end_headers(); self.wfile.write(m)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','*')

    def end_headers(self):
        self.send_header('Cache-Control','no-cache'); super().end_headers()

    def log_message(self, f, *a):
        sys.stderr.write(f"  {'[proxy] ' if '/api/' in str(a[0]) else ''}{a[0]}\n")

def main():
    p = argparse.ArgumentParser(description='AgentChat Server')
    p.add_argument('--port','-p',type=int,default=8819)
    p.add_argument('--api','-a',type=str,default=None, help='Remote API URL, e.g. http://192.168.1.100:8000')
    p.add_argument('--no-browser',action='store_true')
    a = p.parse_args()
    with socketserver.TCPServer(('',a.port),partial(H,api_base=a.api)) as s:
        s.allow_reuse_address = True
        url = f'http://localhost:{a.port}'
        print(f'\n  ⚡ AgentChat → {url}')
        if a.api: print(f'  🔀 Proxy    → {a.api}\n     Endpoint: /api/v1/chat/completions')
        print()
        if not a.no_browser: threading.Timer(.5, lambda: webbrowser.open(url)).start()
        try: s.serve_forever()
        except KeyboardInterrupt: print('\n  Stopped.'); s.shutdown()

if __name__ == '__main__': main()
