"""
KwachaKeeper - Unified API Server
Handles transactions, budgets, and authentication
"""

import json
import sys
import socket
import jwt
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from src.models.database import Database
from src.models.transaction import Transaction, TransactionType, Category
from src.models.auth_db import AuthDatabase

JWT_SECRET = "kwacha-keeper-secret-key-change-in-production"

db = Database()
auth_db = AuthDatabase()


class APIHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def _get_user_id(self):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            payload = auth_db.verify_token(token)
            if payload:
                return payload.get('user_id')
        return None
    
    def do_OPTIONS(self):
        self._set_headers(200)
    
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
            self.wfile.write(json.dumps({'user': user.to_dict(), 'token': token}).encode())
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
            self.wfile.write(json.dumps({'user': user.to_dict(), 'token': token}).encode())
        else:
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Invalid email or password'}).encode())
    
    def do_GET(self):
        if self.path.startswith('/api/transactions'):
            try:
                query = urlparse(self.path).query
                params = parse_qs(query) if query else {}
                
                start_date = None
                end_date = None
                
                if 'start' in params:
                    start_date = datetime.fromisoformat(params['start'][0])
                if 'end' in params:
                    end_date = datetime.fromisoformat(params['end'][0])
                
                transactions = db.get_transactions(start_date=start_date, end_date=end_date)
                self._set_headers(200)
                self.wfile.write(json.dumps([t.to_dict() for t in transactions]).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/balance':
            try:
                balance = db.get_balance()
                self._set_headers(200)
                self.wfile.write(json.dumps({'balance': balance}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/summary':
            try:
                now = datetime.now()
                summary = db.get_monthly_summary(now.year, now.month)
                self._set_headers(200)
                self.wfile.write(json.dumps(summary).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            try:
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT category, amount FROM budgets WHERE month = %s AND year = %s",
                    (datetime.now().month, datetime.now().year)
                )
                budgets = {row[0]: row[1] for row in cursor.fetchall()}
                self._set_headers(200)
                self.wfile.write(json.dumps(budgets).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/export/csv':
            try:
                transactions = db.get_transactions()
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename=kwachakeeper_transactions.csv')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                csv_data = 'Date,Type,Category,Amount,Description\n'
                for t in transactions:
                    desc = t.description.replace(',', ' ').replace('\n', ' ')
                    csv_data += f'{t.date.date()},{t.transaction_type.value},{t.category.value},{t.amount},{desc}\n'
                self.wfile.write(csv_data.encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/health':
            self._set_headers(200)
            self.wfile.write(json.dumps({'status': 'ok', 'auth': True}).encode())
        
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        
        if self.path == '/auth/signup':
            self._handle_signup(post_data)
            return
        elif self.path == '/auth/login':
            self._handle_login(post_data)
            return
        elif self.path == '/auth/verify':
            token = post_data.get('token', '')
            payload = auth_db.verify_token(token)
            if payload:
                self._set_headers(200)
                self.wfile.write(json.dumps({'valid': True, 'user': payload}).encode())
            else:
                self._set_headers(401)
                self.wfile.write(json.dumps({'valid': False}).encode())
            return
        
        if self.path == '/api/transactions':
            try:
                transaction = Transaction(
                    id=None,
                    amount=float(post_data['amount']),
                    transaction_type=TransactionType(post_data['type']),
                    category=Category(post_data['category']),
                    description=post_data.get('description', ''),
                    date=datetime.fromisoformat(post_data['date']) if 'date' in post_data else datetime.now()
                )
                tx_id = db.add_transaction(transaction)
                transaction.id = tx_id
                self._set_headers(201)
                self.wfile.write(json.dumps(transaction.to_dict()).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            try:
                db.set_budget(
                    datetime.now().month, datetime.now().year,
                    post_data['category'], float(post_data['amount'])
                )
                self._set_headers(201)
                self.wfile.write(json.dumps({'status': 'saved'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_PUT(self):
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                content_length = int(self.headers.get('Content-Length', 0))
                put_data = json.loads(self.rfile.read(content_length))
                
                cursor = db.conn.cursor()
                cursor.execute("""
                    UPDATE transactions 
                    SET amount = %s, type = %s, category = %s, description = %s, date = %s
                    WHERE id = %s
                """, (
                    float(put_data['amount']),
                    put_data['type'],
                    put_data['category'],
                    put_data.get('description', ''),
                    put_data.get('date', datetime.now().isoformat()),
                    tx_id
                ))
                db.conn.commit()
                
                if cursor.rowcount > 0:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({'status': 'updated', 'id': tx_id}).encode())
                else:
                    self._set_headers(404)
                    self.wfile.write(json.dumps({'error': 'Transaction not found'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_DELETE(self):
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                cursor = db.conn.cursor()
                cursor.execute("DELETE FROM transactions WHERE id = %s", (tx_id,))
                db.conn.commit()
                if cursor.rowcount > 0:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({'status': 'deleted', 'id': tx_id}).encode())
                else:
                    self._set_headers(404)
                    self.wfile.write(json.dumps({'error': 'Transaction not found'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def log_message(self, format, *args):
        print(f"[API] {args[0]}")


def find_available_port(start_port=5000):
    for port in range(start_port, start_port + 10):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return None


if __name__ == '__main__':
    port = find_available_port(5000)
    if port is None:
        print("No available port found")
        sys.exit(1)
    
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    print(f"KwachaKeeper API running on http://localhost:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.server_close()
        db.close()
        auth_db.close()
