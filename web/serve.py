"""
Alphora Chat Frontend Server

    python serve.py                    # localhost:8813
    python serve.py --port 3000        # custom port
    python serve.py --no-browser       # don't auto open

Backend connection is configured entirely in the frontend UI (API settings).
"""
import argparse, http.server, mimetypes, socketserver, sys, threading, webbrowser
from pathlib import Path

DIR = Path(__file__).parent.resolve()
ROOT = DIR.parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', ''):
            self.path = '/index.html'
        if self.path.startswith('/asset/'):
            return self._serve_asset()
        return super().do_GET()

    def _serve_asset(self):
        rel = self.path.lstrip('/')
        f = (ROOT / rel).resolve()
        if not f.is_file() or ROOT not in f.parents:
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(str(f))
        data = f.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, f, *a):
        sys.stderr.write(f"  {a[0]}\n")


def main():
    p = argparse.ArgumentParser(description='Alphora Chat Frontend Server')
    p.add_argument('--port', '-p', type=int, default=8813)
    p.add_argument('--no-browser', action='store_true')
    a = p.parse_args()

    handler = lambda *args, **kw: Handler(*args, directory=str(DIR), **kw)

    with socketserver.TCPServer(('', a.port), handler) as s:
        s.allow_reuse_address = True
        url = f'http://localhost:{a.port}'
        print(f'\n  Alphora Chat → {url}')
        print(f'  Backend: configure in frontend UI (click ··· in top-right)')
        print()
        if not a.no_browser:
            threading.Timer(.5, lambda: webbrowser.open(url)).start()
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print('\n  Stopped.')
            s.shutdown()


if __name__ == '__main__':
    main()
