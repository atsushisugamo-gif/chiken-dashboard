#!/usr/bin/env python3
"""治験ダッシュボード ローカルサーバー
ブラウザで http://localhost:8765 を開くとダッシュボードが表示されます。
"""
import http.server
import os
import socketserver
import webbrowser
import signal
import sys

PORT = 8765
DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(DIR)

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/dashboard.html'
        return super().do_GET()
    
    def log_message(self, format, *args):
        pass  # サイレント

def signal_handler(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"✅ ダッシュボードサーバー起動: http://localhost:{PORT}")
    print(f"   Ctrl+C で停止")
    webbrowser.open(f"http://localhost:{PORT}")
    httpd.serve_forever()
