"""
KwachaKeeper - Unified API Server
Multi-tenant secure API with wallets, rate limiting, encryption, and audit logs
"""

import json, sys, socket, jwt, time, random, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from src.models.database import Database
from src.models.transaction import Transaction, TransactionType, Category
from src.models.auth_db import AuthDatabase
from src.models.rate_limiter import login_limiter, signup_limiter

JWT_SECRET = "kwacha-keeper-secret-key-change-in-production"
db = Database()
auth_db = AuthDatabase()


def validate_password(password: str) -> str:
    if len(password) < 8: return "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password): return "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password): return "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password): return "Password must contain at least one number"
    return ""


class APIHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def _get_client_ip(self):
        forwarded = self.headers.get('X-Forwarded-For', '')
        return forwarded.split(',')[0].strip() if forwarded else self.client_address[0]
    
    def _get_tenant_id(self):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            payload = auth_db.verify_token(auth_header[7:])
            if payload: return payload.get('tenant_id')
        return None
    
    def _get_user_id(self):
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            payload = auth_db.verify_token(auth_header[7:])
            if payload: return payload.get('user_id')
        return None
    
    def do_OPTIONS(self): self._set_headers(200)
    
    def _handle_signup(self, data):
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        if not email or not password:
            self._set_headers(400); self.wfile.write(json.dumps({'error': 'Email and password required'}).encode()); return
        pw_err = validate_password(password)
        if pw_err:
            self._set_headers(400); self.wfile.write(json.dumps({'error': pw_err}).encode()); return
        if not signup_limiter.is_allowed(self._get_client_ip()):
            self._set_headers(429); self.wfile.write(json.dumps({'error': 'Too many signup attempts'}).encode()); return
        try:
            user = auth_db.create_user(email, password)
            token = auth_db.generate_token(user)
            refresh = auth_db.generate_refresh_token(user)
            db.create_wallet(user.tenant_id, 'Main Wallet', 'cash', 'fa-wallet', '#4CAF50')
            # Create default wallets for new user
            self._set_headers(201)
            self.wfile.write(json.dumps({'user': user.to_dict(), 'token': token, 'refresh_token': refresh}).encode())
        except Exception as e:
            self._set_headers(400); self.wfile.write(json.dumps({'error': 'Email already registered'}).encode())
    
    def _handle_login(self, data):
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        if not login_limiter.is_allowed(self._get_client_ip()):
            self._set_headers(429); self.wfile.write(json.dumps({'error': 'Too many attempts'}).encode()); return
        token = auth_db.authenticate(email, password)
        if token:
            login_limiter.reset(self._get_client_ip())
            user = auth_db.get_user_by_email(email)
            refresh = auth_db.generate_refresh_token(user)
            db.create_wallet(user.tenant_id, 'Main Wallet', 'cash', 'fa-wallet', '#4CAF50')
            self._set_headers(200)
            self.wfile.write(json.dumps({'user': user.to_dict(), 'token': token, 'refresh_token': refresh}).encode())
        else:
            self._set_headers(401); self.wfile.write(json.dumps({'error': 'Invalid credentials'}).encode())
    
    def _generate_tip(self, tenant_id):
        now = datetime.now()
        s = db.get_monthly_summary(now.year, now.month, tenant_id)
        tips = []
        if s['total_expenses'] > 0 and s['total_income'] > 0:
            r = (s['total_expenses']/s['total_income'])*100
            if r > 80: tips.append("Expenses over 80% of income.")
            elif r < 30: tips.append("Great savings rate. Consider investing.")
        if s['total_income'] > 0:
            sv = s['total_income'] - s['total_expenses']
            if sv <= 0: tips.append("No savings. Start with MK5,000 weekly.")
            elif sv < s['total_income']*0.1: tips.append("Aim for 10% savings rate.")
        if not tips: tips.append("Track every expense. Small ones add up.")
        return {'tip': random.choice(tips), 'month': now.strftime('%B %Y'),
                'total_income': s['total_income'], 'total_expenses': s['total_expenses']}
    
    def do_GET(self):
        tenant_id = self._get_tenant_id()
        
        if self.path.startswith('/api/transactions'):
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                query = urlparse(self.path).query
                params = parse_qs(query) if query else {}
                start_date = datetime.fromisoformat(params['start'][0]) if 'start' in params else None
                end_date = datetime.fromisoformat(params['end'][0]) if 'end' in params else None
                wallet_id = int(params['wallet'][0]) if 'wallet' in params else None
                transactions = db.get_transactions(tenant_id=tenant_id, wallet_id=wallet_id, start_date=start_date, end_date=end_date)
                self._set_headers(200); self.wfile.write(json.dumps([t.to_dict() for t in transactions]).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/balance':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                balance = db.get_balance(tenant_id)
                self._set_headers(200); self.wfile.write(json.dumps({'balance': balance}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/wallets':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                wallets = db.get_wallets(tenant_id)
                self._set_headers(200); self.wfile.write(json.dumps(wallets).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/summary':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                now = datetime.now()
                self._set_headers(200); self.wfile.write(json.dumps(db.get_monthly_summary(now.year, now.month, tenant_id)).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/tip':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try: self._set_headers(200); self.wfile.write(json.dumps(self._generate_tip(tenant_id)).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT category, amount FROM budgets WHERE tenant_id=? AND month=? AND year=?",
                             (tenant_id, datetime.now().month, datetime.now().year))
                budgets = {row[0]: row[1] for row in cursor.fetchall()}
                self._set_headers(200); self.wfile.write(json.dumps(budgets).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/recurring':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM recurring WHERE tenant_id=? ORDER BY next_date", (tenant_id,))
                items = [{'id': r[0], 'amount': r[2], 'type': r[3], 'category': r[4], 'description': r[5], 'frequency': r[6], 'next_date': r[7]} for r in cursor.fetchall()]
                self._set_headers(200); self.wfile.write(json.dumps(items).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/goals':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM savings_goals WHERE tenant_id=? ORDER BY created_at DESC", (tenant_id,))
                items = [{'id': r[0], 'name': r[2], 'target_amount': r[3], 'current_amount': r[4], 'deadline': r[5], 'created_at': r[6]} for r in cursor.fetchall()]
                self._set_headers(200); self.wfile.write(json.dumps(items).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/export/csv':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                transactions = db.get_transactions(tenant_id=tenant_id)
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename=kwachakeeper_transactions.csv')
                self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
                csv_data = 'Date,Type,Category,Amount,Description\n'
                for t in transactions:
                    csv_data += f'{t.date.date()},{t.transaction_type.value},{t.category.value},{t.amount},{t.description.replace(","," ")}\n'
                self.wfile.write(csv_data.encode('utf-8'))
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/report/pdf':
            if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.units import mm
                import io
                now = datetime.now()
                s = db.get_monthly_summary(now.year, now.month, tenant_id)
                transactions = db.get_transactions(tenant_id=tenant_id)
                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
                styles = getSampleStyleSheet()
                elements = [Paragraph('KwachaKeeper', ParagraphStyle('T', fontSize=22, textColor=colors.HexColor('#1e3a5f'))),
                           Paragraph(f'Report - {now.strftime("%B %Y")}', ParagraphStyle('ST', fontSize=12, textColor=colors.HexColor('#64748b'))),
                           Spacer(1, 10)]
                sd = [['Balance', 'Income', 'Expenses', 'Net'],
                      [f'MK {s["total_income"]-s["total_expenses"]:,.2f}', f'MK {s["total_income"]:,.2f}', f'MK {s["total_expenses"]:,.2f}', f'MK {s["net_savings"]:,.2f}']]
                st = Table(sd, colWidths=[120]*4)
                st.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#6366f1')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ALIGN',(0,0),(-1,-1),'CENTER'),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#e2e8f0'))]))
                elements.append(st)
                doc.build(elements)
                self.send_response(200); self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename=kwachakeeper_report_{now.strftime("%B_%Y")}.pdf')
                self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()
                self.wfile.write(buf.getvalue()); buf.close()
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/health': self._set_headers(200); self.wfile.write(json.dumps({'status': 'ok'}).encode())
        else: self._set_headers(404); self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
        
        if self.path == '/auth/signup': self._handle_signup(post_data); return
        elif self.path == '/auth/login': self._handle_login(post_data); return
        elif self.path == '/auth/refresh':
            payload = auth_db.verify_token(post_data.get('refresh_token', ''))
            if payload:
                user = auth_db.get_user_by_email(payload.get('email', ''))
                if user: self._set_headers(200); self.wfile.write(json.dumps({'token': auth_db.generate_token(user)}).encode()); return
            self._set_headers(401); self.wfile.write(json.dumps({'error': 'Invalid'}).encode()); return
        elif self.path == '/auth/verify':
            payload = auth_db.verify_token(post_data.get('token', ''))
            if payload: self._set_headers(200); self.wfile.write(json.dumps({'valid': True, 'user': payload}).encode())
            else: self._set_headers(401); self.wfile.write(json.dumps({'valid': False}).encode())
            return
        
        tenant_id = self._get_tenant_id()
        if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
        
        if self.path == '/api/transactions':
            try:
                wallet_id = post_data.get('wallet_id', 1)
                transaction = Transaction(None, float(post_data['amount']),
                    TransactionType(post_data['type']), Category(post_data['category']),
                    post_data.get('description', ''),
                    datetime.fromisoformat(post_data['date']) if 'date' in post_data else datetime.now())
                tx_id = db.add_transaction(transaction, tenant_id, wallet_id)
                transaction.id = tx_id
                self._set_headers(201); self.wfile.write(json.dumps(transaction.to_dict()).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/wallets':
            try:
                wallet_id = db.create_wallet(tenant_id, post_data['name'], post_data.get('type', 'cash'),
                                            post_data.get('icon', 'fa-wallet'), post_data.get('color', '#4CAF50'))
                self._set_headers(201); self.wfile.write(json.dumps({'status': 'created', 'id': wallet_id}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            try:
                db.set_budget(datetime.now().month, datetime.now().year, post_data['category'], float(post_data['amount']), tenant_id)
                self._set_headers(201); self.wfile.write(json.dumps({'status': 'saved'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/recurring':
            try:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO recurring (tenant_id, wallet_id, amount, type, category, description, frequency, next_date, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (tenant_id, post_data.get('wallet_id', 1), float(post_data['amount']), post_data['type'],
                              post_data['category'], post_data.get('description', ''), post_data.get('frequency', 'monthly'),
                              post_data.get('next_date', datetime.now().isoformat()), datetime.now().isoformat()))
                db.conn.commit()
                self._set_headers(201); self.wfile.write(json.dumps({'status': 'created'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/goals':
            try:
                cursor = db.conn.cursor()
                cursor.execute("INSERT INTO savings_goals (tenant_id, name, target_amount, current_amount, deadline, created_at) VALUES (?,?,?,0,?,?)",
                             (tenant_id, post_data['name'], float(post_data['target_amount']), post_data.get('deadline', ''), datetime.now().isoformat()))
                db.conn.commit()
                self._set_headers(201); self.wfile.write(json.dumps({'status': 'created'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path.startswith('/api/goals/') and self.path.endswith('/add'):
            try:
                goal_id = int(self.path.split('/')[-2])
                cursor = db.conn.cursor()
                cursor.execute("UPDATE savings_goals SET current_amount = current_amount + ? WHERE id=? AND tenant_id=?",
                             (float(post_data.get('amount', 0)), goal_id, tenant_id))
                db.conn.commit(); self._set_headers(200); self.wfile.write(json.dumps({'status': 'updated'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else: self._set_headers(404); self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_PUT(self):
        tenant_id = self._get_tenant_id()
        if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                put_data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                cursor = db.conn.cursor()
                cursor.execute("UPDATE transactions SET amount=?, type=?, category=?, description=?, date=? WHERE id=? AND tenant_id=?",
                             (float(put_data['amount']), put_data['type'], put_data['category'], put_data.get('description', ''),
                              put_data.get('date', datetime.now().isoformat()), tx_id, tenant_id))
                db.conn.commit()
                self._set_headers(200) if cursor.rowcount > 0 else self._set_headers(404)
                self.wfile.write(json.dumps({'status': 'updated'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        else: self._set_headers(404); self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_DELETE(self):
        tenant_id = self._get_tenant_id()
        if not tenant_id: self._set_headers(401); self.wfile.write(json.dumps({'error': 'Auth required'}).encode()); return
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                cursor = db.conn.cursor()
                cursor.execute("DELETE FROM transactions WHERE id=? AND tenant_id=?", (tx_id, tenant_id))
                db.conn.commit()
                self._set_headers(200) if cursor.rowcount > 0 else self._set_headers(404)
                self.wfile.write(json.dumps({'status': 'deleted'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif self.path.startswith('/api/wallets/'):
            try:
                wallet_id = int(self.path.split('/')[-1])
                db.delete_wallet(wallet_id, tenant_id)
                self._set_headers(200); self.wfile.write(json.dumps({'status': 'deleted'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif self.path.startswith('/api/recurring/'):
            try:
                rid = int(self.path.split('/')[-1])
                db.conn.cursor().execute("DELETE FROM recurring WHERE id=? AND tenant_id=?", (rid, tenant_id))
                db.conn.commit(); self._set_headers(200); self.wfile.write(json.dumps({'status': 'deleted'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif self.path.startswith('/api/goals/'):
            try:
                gid = int(self.path.split('/')[-1])
                db.conn.cursor().execute("DELETE FROM savings_goals WHERE id=? AND tenant_id=?", (gid, tenant_id))
                db.conn.commit(); self._set_headers(200); self.wfile.write(json.dumps({'status': 'deleted'}).encode())
            except Exception as e: self._set_headers(500); self.wfile.write(json.dumps({'error': str(e)}).encode())
        else: self._set_headers(404); self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def log_message(self, format, *args): pass


def find_available_port(start_port=5000):
    for port in range(start_port, start_port + 10):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port)); return port
        except OSError: continue
    return None

if __name__ == '__main__':
    port = find_available_port(5000)
    if port is None: print("No port"); sys.exit(1)
    HTTPServer(('0.0.0.0', port), APIHandler).serve_forever()
