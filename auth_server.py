"""
KwachaKeeper - Authentication API Server
Handles user signup, login, and token verification
"""

import json
import sys
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from src.models.auth_db import AuthDatabase

auth_db = AuthDatabase()


class AuthHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def do_OPTIONS(self):
        self._set_headers(200)
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        
        if self.path == '/auth/signup':
            self._handle_signup(post_data)
        elif self.path == '/auth/login':
            self._handle_login(post_data)
        elif self.path == '/auth/verify':
            self._handle_verify(post_data)
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def _handle_signup(self, data):
        email = data.get('email', '')
        password = data.get('password', '')
        
        if not email or not password:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Email and password required'}).encode())
            return
        
        if len(password) < 6:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Password must be at least 6 characters'}).encode())
            return
        
        try:
            user = auth_db.create_user(email, password)
            token = auth_db.generate_token(user)
            
            self._set_headers(201)
            self.wfile.write(json.dumps({
                'user': user.to_dict(),
                'token': token
            }).encode())
        except Exception as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Email already registered'}).encode())
    
    def _handle_login(self, data):
        email = data.get('email', '')
        password = data.get('password', '')
        
        token = auth_db.authenticate(email, password)
        
        if token:
            user = auth_db.get_user_by_email(email)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                'user': user.to_dict(),
                'token': token
            }).encode())
        else:
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Invalid email or password'}).encode())
    
    def _handle_verify(self, data):
        token = data.get('token', '')
        payload = auth_db.verify_token(token)
        
        if payload:
            self._set_headers(200)
            self.wfile.write(json.dumps({'valid': True, 'user': payload}).encode())
        else:
            self._set_headers(401)
            self.wfile.write(json.dumps({'valid': False}).encode())
    
    def log_message(self, format, *args):
        print(f"[Auth] {args[0]}")


def find_available_port(start_port=5001):
    for port in range(start_port, start_port + 10):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return None


if __name__ == '__main__':
    port = find_available_port(5001)
    
    if port is None:
        print("No available port found")
        sys.exit(1)
    
    server = HTTPServer(('0.0.0.0', port), AuthHandler)
    print(f"Auth API running on http://localhost:{port}")
    print(f"Endpoints:")
    print(f"  POST /auth/signup")
    print(f"  POST /auth/login")
    print(f"  POST /auth/verify")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAuth server stopped")
        server.server_close()
        auth_db.close()
