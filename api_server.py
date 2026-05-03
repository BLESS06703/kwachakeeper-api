"""
KwachaKeeper - Unified API Server
Handles transactions, budgets, and authentication
"""

import json
import sys
import socket
import jwt
import time
import random
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
    
    def _generate_tip(self):
        """Generate a financial tip based on spending patterns"""
        now = datetime.now()
        summary = db.get_monthly_summary(now.year, now.month)
        transactions = db.get_transactions()
        
        total_income = summary['total_income']
        total_expenses = summary['total_expenses']
        expenses_by_cat = summary['expenses_by_category']
        
        tips = []
        
        # Calculate percentages
        if total_expenses > 0 and total_income > 0:
            expense_ratio = (total_expenses / total_income) * 100
            
            if expense_ratio > 80:
                tips.append("Your expenses are over 80% of your income this month. Try to keep spending below 70% to build savings.")
            elif expense_ratio < 30:
                tips.append("You're saving a lot this month. Consider investing some of your savings to grow your wealth.")
        
        # Category-specific tips
        for category, amount in expenses_by_cat.items():
            pct = (amount / total_expenses * 100) if total_expenses > 0 else 0
            
            if category == 'Food & Groceries' and pct > 40:
                tips.append("Food takes up a big portion of your budget. Buying in bulk at Shoprite or local markets can reduce costs.")
            elif category == 'Transport (Minibus/Fuel)' and pct > 25:
                tips.append("Transport costs are significant. Consider a monthly minibus pass or carpooling to save money.")
            elif category == 'Airtime & Data' and pct > 15:
                tips.append("You're spending a lot on airtime. TNM and Airtel offer monthly bundles that could save you up to 30%.")
            elif category == 'Utilities (ESCOM/Water)' and amount > 50000:
                tips.append("High utility bill detected. Switch to energy-saving bulbs and fix water leaks to reduce monthly costs.")
        
        # Savings tip
        if total_income > 0:
            savings = total_income - total_expenses
            if savings <= 0:
                tips.append("No savings this month. Start small: put aside MK5,000 each week into a separate account.")
            elif savings < total_income * 0.1:
                tips.append("You saved a bit this month. Aim to save at least 10% of your income for emergencies.")
        
        # Generic tips if no specific ones
        if not tips:
            generic_tips = [
                "Track every expense, even small ones. They add up quickly.",
                "Set aside an emergency fund of at least 3 months of expenses.",
                "Review your subscriptions monthly and cancel what you don't use.",
                "Plan your meals for the week to avoid impulse food purchases.",
                "Use cash for daily expenses - it makes spending feel more real.",
                "Compare prices before buying. A few minutes of research can save thousands.",
                "Avoid buying airtime in small amounts. Bulk bundles are cheaper per MB.",
                "Start a side hustle. Even MK20,000 extra per month makes a difference."
            ]
            tips.append(random.choice(generic_tips))
        
        return {
            'tip': random.choice(tips),
            'month': now.strftime('%B %Y'),
            'total_income': total_income,
            'total_expenses': total_expenses
        }
    
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
        
        elif self.path == '/api/tip':
            try:
                tip = self._generate_tip()
                self._set_headers(200)
                self.wfile.write(json.dumps(tip).encode())
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
                    SET amount = ?, type = ?, category = ?, description = ?, date = ?
                    WHERE id = ?
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
                cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
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
