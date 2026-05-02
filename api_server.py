"""
KwachaKeeper API Server
Connects React frontend to SQLite database
"""

import json
import sys
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from src.models.database import Database
from src.models.transaction import Transaction, TransactionType, Category

db = Database()

class APIHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_OPTIONS(self):
        self._set_headers(200)
    
    def do_GET(self):
        if self.path == '/api/transactions':
            try:
                transactions = db.get_transactions()
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
                    "SELECT category, amount FROM budgets WHERE month = ? AND year = ?", 
                    (datetime.now().month, datetime.now().year)
                )
                budgets = {row[0]: row[1] for row in cursor.fetchall()}
                self._set_headers(200)
                self.wfile.write(json.dumps(budgets).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/health':
            self._set_headers(200)
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
        
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_POST(self):
        if self.path == '/api/transactions':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({'error': 'Empty request body'}).encode())
                    return
                
                post_data = json.loads(self.rfile.read(content_length))
                
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
                print(f"Transaction saved: {transaction}")
                
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = json.loads(self.rfile.read(content_length))
                
                db.set_budget(
                    datetime.now().month,
                    datetime.now().year,
                    post_data['category'],
                    float(post_data['amount'])
                )
                
                self._set_headers(201)
                self.wfile.write(json.dumps({'status': 'saved'}).encode())
                print(f"Budget saved: {post_data['category']} = MK{post_data['amount']}")
                
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
                cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
                db.conn.commit()
                
                if cursor.rowcount > 0:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({'status': 'deleted', 'id': tx_id}).encode())
                    print(f"Transaction {tx_id} deleted")
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
    print(f"Endpoints:")
    print(f"  GET    /api/health")
    print(f"  GET    /api/balance")
    print(f"  GET    /api/summary")
    print(f"  GET    /api/transactions")
    print(f"  GET    /api/budgets")
    print(f"  POST   /api/transactions")
    print(f"  POST   /api/budgets")
    print(f"  DELETE /api/transactions/:id")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
        server.server_close()
        db.close()
