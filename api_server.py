"""
KwachaKeeper - Unified API Server
Multi-tenant secure API with JWT auth, rate limiting, and password policies
"""

import json
import sys
import socket
import jwt
import time
import random
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from src.models.database import Database
from src.models.transaction import Transaction, TransactionType, Category
from src.models.auth_db import AuthDatabase
from src.models.rate_limiter import login_limiter, signup_limiter

JWT_SECRET = "kwacha-keeper-secret-key-change-in-production"
JWT_REFRESH_EXPIRY = 30 * 24 * 60 * 60  # 30 days

db = Database()
auth_db = AuthDatabase()


def validate_password(password: str) -> str:
    """Validate password strength. Returns error message or empty string."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one number"
    return ""


class APIHandler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', 'https://kwachakeeper.netlify.app')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
    
    def _get_client_ip(self):
        """Get client IP address"""
        forwarded = self.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return self.client_address[0]
    
    def _get_tenant_id(self):
        """Extract tenant_id from Authorization header"""
        auth_header = self.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            payload = auth_db.verify_token(token)
            if payload:
                return payload.get('tenant_id')
        return None
    
    def do_OPTIONS(self):
        self._set_headers(200)
    
    def _handle_signup(self, data):
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        client_ip = self._get_client_ip()
        
        if not email or not password:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Email and password required'}).encode())
            return
        
        # Password strength check
        password_error = validate_password(password)
        if password_error:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': password_error}).encode())
            return
        
        # Rate limiting
        if not signup_limiter.is_allowed(client_ip):
            self._set_headers(429)
            self.wfile.write(json.dumps({
                'error': 'Too many signup attempts. Try again later.',
                'retry_after': '2 minutes'
            }).encode())
            return
        
        try:
            user = auth_db.create_user(email, password)
            token = auth_db.generate_token(user)
            refresh_token = auth_db.generate_refresh_token(user)
            self._set_headers(201)
            self.wfile.write(json.dumps({
                'user': user.to_dict(),
                'token': token,
                'refresh_token': refresh_token
            }).encode())
        except Exception as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Email already registered'}).encode())
    
    def _handle_login(self, data):
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        client_ip = self._get_client_ip()
        
        if not email or not password:
            self._set_headers(400)
            self.wfile.write(json.dumps({'error': 'Email and password required'}).encode())
            return
        
        # Rate limiting
        if not login_limiter.is_allowed(client_ip):
            remaining = login_limiter.remaining(client_ip)
            self._set_headers(429)
            self.wfile.write(json.dumps({
                'error': f'Too many login attempts. {remaining} attempts remaining.',
                'retry_after': '1 minute'
            }).encode())
            return
        
        token = auth_db.authenticate(email, password)
        if token:
            login_limiter.reset(client_ip)
            user = auth_db.get_user_by_email(email)
            refresh_token = auth_db.generate_refresh_token(user)
            self._set_headers(200)
            self.wfile.write(json.dumps({
                'user': user.to_dict(),
                'token': token,
                'refresh_token': refresh_token
            }).encode())
        else:
            self._set_headers(401)
            self.wfile.write(json.dumps({
                'error': 'Invalid email or password',
                'attempts_remaining': login_limiter.remaining(client_ip)
            }).encode())
    
    def _generate_tip(self, tenant_id):
        now = datetime.now()
        summary = db.get_monthly_summary(now.year, now.month, tenant_id)
        total_income = summary['total_income']
        total_expenses = summary['total_expenses']
        expenses_by_cat = summary['expenses_by_category']
        tips = []
        if total_expenses > 0 and total_income > 0:
            expense_ratio = (total_expenses / total_income) * 100
            if expense_ratio > 80:
                tips.append("Your expenses are over 80% of your income this month.")
            elif expense_ratio < 30:
                tips.append("You're saving a lot this month. Consider investing.")
        for category, amount in expenses_by_cat.items():
            pct = (amount / total_expenses * 100) if total_expenses > 0 else 0
            if category == 'Food & Groceries' and pct > 40:
                tips.append("Food takes up a big portion. Try buying in bulk at Shoprite.")
            elif category == 'Transport (Minibus/Fuel)' and pct > 25:
                tips.append("Transport costs are high. Consider a monthly minibus pass.")
            elif category == 'Airtime & Data' and pct > 15:
                tips.append("Monthly bundles save up to 30% on airtime.")
        if total_income > 0:
            savings = total_income - total_expenses
            if savings <= 0:
                tips.append("No savings this month. Start with MK5,000 weekly.")
            elif savings < total_income * 0.1:
                tips.append("Aim to save at least 10% of your income.")
        if not tips:
            generic_tips = [
                "Track every expense. Small ones add up quickly.",
                "Set aside an emergency fund of 3 months of expenses.",
                "Plan meals for the week to avoid impulse purchases.",
                "Compare prices before buying. Research saves thousands.",
                "Start a side hustle. Extra MK20,000 makes a difference."
            ]
            tips.append(random.choice(generic_tips))
        return {
            'tip': random.choice(tips),
            'month': now.strftime('%B %Y'),
            'total_income': total_income,
            'total_expenses': total_expenses
        }
    
    def do_GET(self):
        tenant_id = self._get_tenant_id()
        
        if self.path.startswith('/api/transactions'):
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                query = urlparse(self.path).query
                params = parse_qs(query) if query else {}
                start_date = None
                end_date = None
                if 'start' in params:
                    start_date = datetime.fromisoformat(params['start'][0])
                if 'end' in params:
                    end_date = datetime.fromisoformat(params['end'][0])
                transactions = db.get_transactions(tenant_id=tenant_id, start_date=start_date, end_date=end_date)
                self._set_headers(200)
                self.wfile.write(json.dumps([t.to_dict() for t in transactions]).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/balance':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                balance = db.get_balance(tenant_id)
                self._set_headers(200)
                self.wfile.write(json.dumps({'balance': balance}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/summary':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                now = datetime.now()
                summary = db.get_monthly_summary(now.year, now.month, tenant_id)
                self._set_headers(200)
                self.wfile.write(json.dumps(summary).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/tip':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                tip = self._generate_tip(tenant_id)
                self._set_headers(200)
                self.wfile.write(json.dumps(tip).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT category, amount FROM budgets WHERE tenant_id = ? AND month = ? AND year = ?",
                    (tenant_id, datetime.now().month, datetime.now().year)
                )
                budgets = {row[0]: row[1] for row in cursor.fetchall()}
                self._set_headers(200)
                self.wfile.write(json.dumps(budgets).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/recurring':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM recurring WHERE tenant_id = ? ORDER BY next_date", (tenant_id,))
                recurring = []
                for row in cursor.fetchall():
                    recurring.append({
                        'id': row[0], 'amount': row[2], 'type': row[3],
                        'category': row[4], 'description': row[5],
                        'frequency': row[6], 'next_date': row[7]
                    })
                self._set_headers(200)
                self.wfile.write(json.dumps(recurring).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/goals':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM savings_goals WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,))
                goals = []
                for row in cursor.fetchall():
                    goals.append({
                        'id': row[0], 'name': row[2], 'target_amount': row[3],
                        'current_amount': row[4], 'deadline': row[5], 'created_at': row[6]
                    })
                self._set_headers(200)
                self.wfile.write(json.dumps(goals).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/export/csv':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                transactions = db.get_transactions(tenant_id=tenant_id)
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename=kwachakeeper_transactions.csv')
                self.send_header('Access-Control-Allow-Origin', 'https://kwachakeeper.netlify.app')
                self.end_headers()
                csv_data = 'Date,Type,Category,Amount,Description\n'
                for t in transactions:
                    desc = t.description.replace(',', ' ').replace('\n', ' ')
                    csv_data += f'{t.date.date()},{t.transaction_type.value},{t.category.value},{t.amount},{desc}\n'
                self.wfile.write(csv_data.encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/report/pdf':
            if not tenant_id:
                self._set_headers(401)
                self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
                return
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.units import mm
                import io
                now = datetime.now()
                summary = db.get_monthly_summary(now.year, now.month, tenant_id)
                transactions = db.get_transactions(tenant_id=tenant_id)
                buf = io.BytesIO()
                doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
                styles = getSampleStyleSheet()
                elements = []
                title_style = ParagraphStyle('Title', fontSize=22, textColor=colors.HexColor('#1e3a5f'), spaceAfter=6)
                subtitle_style = ParagraphStyle('Subtitle', fontSize=12, textColor=colors.HexColor('#64748b'), spaceAfter=20)
                elements.append(Paragraph('KwachaKeeper', title_style))
                elements.append(Paragraph(f'Monthly Report - {now.strftime("%B %Y")}', subtitle_style))
                elements.append(Spacer(1, 10))
                summary_data = [
                    ['Balance', 'Income', 'Expenses', 'Net Savings'],
                    [f'MK {summary["total_income"] - summary["total_expenses"]:,.2f}',
                     f'MK {summary["total_income"]:,.2f}',
                     f'MK {summary["total_expenses"]:,.2f}',
                     f'MK {summary["net_savings"]:,.2f}']
                ]
                summary_table = Table(summary_data, colWidths=[120, 120, 120, 120])
                summary_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('TOPPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ]))
                elements.append(summary_table)
                elements.append(Spacer(1, 20))
                elements.append(Paragraph('Transactions', styles['Heading2']))
                elements.append(Spacer(1, 8))
                tx_data = [['Date', 'Type', 'Category', 'Amount', 'Description']]
                for t in transactions[:30]:
                    tx_data.append([str(t.date.date()), t.transaction_type.value.capitalize(), t.category.value[:25], f'MK {t.amount:,.2f}', t.description[:30]])
                tx_table = Table(tx_data, colWidths=[80, 55, 120, 100, 145])
                tx_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cbd5e1')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ]))
                elements.append(tx_table)
                doc.build(elements)
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename=kwachakeeper_report_{now.strftime("%B_%Y")}.pdf')
                self.send_header('Access-Control-Allow-Origin', 'https://kwachakeeper.netlify.app')
                self.end_headers()
                self.wfile.write(buf.getvalue())
                buf.close()
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
        elif self.path == '/auth/refresh':
            token = post_data.get('refresh_token', '')
            payload = auth_db.verify_token(token)
            if payload:
                user = auth_db.get_user_by_email(payload.get('email', ''))
                if user:
                    new_token = auth_db.generate_token(user)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({'token': new_token}).encode())
                    return
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Invalid refresh token'}).encode())
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
        
        tenant_id = self._get_tenant_id()
        if not tenant_id:
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
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
                tx_id = db.add_transaction(transaction, tenant_id)
                transaction.id = tx_id
                self._set_headers(201)
                self.wfile.write(json.dumps(transaction.to_dict()).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/budgets':
            try:
                db.set_budget(datetime.now().month, datetime.now().year, post_data['category'], float(post_data['amount']), tenant_id)
                self._set_headers(201)
                self.wfile.write(json.dumps({'status': 'saved'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/recurring':
            try:
                cursor = db.conn.cursor()
                cursor.execute("""
                    INSERT INTO recurring (tenant_id, amount, type, category, description, frequency, next_date, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (tenant_id, float(post_data['amount']), post_data['type'], post_data['category'],
                     post_data.get('description', ''), post_data.get('frequency', 'monthly'),
                     post_data.get('next_date', datetime.now().isoformat()), datetime.now().isoformat()))
                db.conn.commit()
                self._set_headers(201)
                self.wfile.write(json.dumps({'status': 'created', 'id': cursor.lastrowid}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path == '/api/goals':
            try:
                cursor = db.conn.cursor()
                cursor.execute("""
                    INSERT INTO savings_goals (tenant_id, name, target_amount, current_amount, deadline, created_at)
                    VALUES (?, ?, ?, 0, ?, ?)
                """, (tenant_id, post_data['name'], float(post_data['target_amount']),
                     post_data.get('deadline', ''), datetime.now().isoformat()))
                db.conn.commit()
                self._set_headers(201)
                self.wfile.write(json.dumps({'status': 'created', 'id': cursor.lastrowid}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        elif self.path.startswith('/api/goals/') and self.path.endswith('/add'):
            try:
                goal_id = int(self.path.split('/')[-2])
                cursor = db.conn.cursor()
                cursor.execute(
                    "UPDATE savings_goals SET current_amount = current_amount + ? WHERE id = ? AND tenant_id = ?",
                    (float(post_data.get('amount', 0)), goal_id, tenant_id)
                )
                db.conn.commit()
                self._set_headers(200)
                self.wfile.write(json.dumps({'status': 'updated'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode())
    
    def do_PUT(self):
        tenant_id = self._get_tenant_id()
        if not tenant_id:
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
            return
        
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                content_length = int(self.headers.get('Content-Length', 0))
                put_data = json.loads(self.rfile.read(content_length))
                cursor = db.conn.cursor()
                cursor.execute("""
                    UPDATE transactions SET amount = ?, type = ?, category = ?, description = ?, date = ?
                    WHERE id = ? AND tenant_id = ?
                """, (float(put_data['amount']), put_data['type'], put_data['category'],
                     put_data.get('description', ''), put_data.get('date', datetime.now().isoformat()),
                     tx_id, tenant_id))
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
        tenant_id = self._get_tenant_id()
        if not tenant_id:
            self._set_headers(401)
            self.wfile.write(json.dumps({'error': 'Authentication required'}).encode())
            return
        
        if self.path.startswith('/api/transactions/'):
            try:
                tx_id = int(self.path.split('/')[-1])
                cursor = db.conn.cursor()
                cursor.execute("DELETE FROM transactions WHERE id = ? AND tenant_id = ?", (tx_id, tenant_id))
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
        elif self.path.startswith('/api/recurring/'):
            try:
                rec_id = int(self.path.split('/')[-1])
                cursor = db.conn.cursor()
                cursor.execute("DELETE FROM recurring WHERE id = ? AND tenant_id = ?", (rec_id, tenant_id))
                db.conn.commit()
                self._set_headers(200)
                self.wfile.write(json.dumps({'status': 'deleted'}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        elif self.path.startswith('/api/goals/'):
            try:
                goal_id = int(self.path.split('/')[-1])
                cursor = db.conn.cursor()
                cursor.execute("DELETE FROM savings_goals WHERE id = ? AND tenant_id = ?", (goal_id, tenant_id))
                db.conn.commit()
                self._set_headers(200)
                self.wfile.write(json.dumps({'status': 'deleted'}).encode())
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
