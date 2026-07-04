"""
KwachaKeeper - SQLite Database Manager
Multi-tenant secure database with encryption and audit logs
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional
from src.models.encryption import encrypt, decrypt
from .transaction import Transaction, TransactionType, Category


class Database:
    """SQLite database manager for KwachaKeeper"""
    
    def __init__(self, db_path: str = "kwacha_keeper.db"):
        self.db_path = db_path
        self.conn = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Create tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(tenant_id, month, year, category),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                frequency TEXT NOT NULL DEFAULT 'monthly',
                next_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')
        
        # Audit logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                user_id INTEGER,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Active sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                device_info TEXT,
                ip_address TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        cursor.execute("SELECT COUNT(*) FROM tenants")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO tenants (name, created_at) VALUES (?, ?)", 
                         ('Default', datetime.now().isoformat()))
        
        self.conn.commit()
    
    def log_audit(self, tenant_id: int, user_id: int, action: str, resource: str, details: str = '', ip_address: str = ''):
        """Record an audit log entry"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO audit_logs (tenant_id, user_id, action, resource, details, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (tenant_id, user_id, action, resource, details, ip_address, datetime.now().isoformat()))
        self.conn.commit()
    
    def get_audit_logs(self, tenant_id: int, limit: int = 50) -> list:
        """Get audit logs for a tenant"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM audit_logs WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def add_session(self, tenant_id: int, user_id: int, token_hash: str, ip_address: str = '', device_info: str = '') -> int:
        """Track an active session"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (tenant_id, user_id, token_hash, device_info, ip_address, is_active, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        ''', (tenant_id, user_id, token_hash, device_info, ip_address, 
              datetime.now().isoformat(), 
              (datetime.now() + timedelta(days=7)).isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def revoke_session(self, session_id: int, tenant_id: int):
        """Revoke a session"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE sessions SET is_active = 0 WHERE id = ? AND tenant_id = ?", 
                     (session_id, tenant_id))
        self.conn.commit()
    
    def get_active_sessions(self, tenant_id: int, user_id: int) -> list:
        """Get active sessions for a user"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE tenant_id = ? AND user_id = ? AND is_active = 1",
            (tenant_id, user_id)
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def add_transaction(self, transaction: Transaction, tenant_id: int = 1) -> int:
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (tenant_id, amount, type, category, description, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (tenant_id, transaction.amount, transaction.transaction_type.value,
             transaction.category.value, encrypt(transaction.description),
             transaction.date.isoformat(), transaction.created_at.isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_transactions(self, tenant_id: int = 1, start_date=None, end_date=None,
                        transaction_type=None, category=None) -> List[Transaction]:
        query = "SELECT * FROM transactions WHERE tenant_id = ?"
        params = [tenant_id]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        if transaction_type:
            query += " AND type = ?"
            params.append(transaction_type.value)
        if category:
            query += " AND category = ?"
            params.append(category.value)
        query += " ORDER BY date DESC"
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        transactions = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            row_dict["description"] = decrypt(row_dict.get("description", ""))
            transactions.append(Transaction.from_dict(row_dict))
        return transactions
    
    def get_balance(self, tenant_id: int = 1) -> float:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                   COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as balance
            FROM transactions WHERE tenant_id = ?
        """, (tenant_id,))
        result = cursor.fetchone()
        return result[0] if result else 0.0
    
    def get_monthly_summary(self, year: int, month: int, tenant_id: int = 1) -> dict:
        cursor = self.conn.cursor()
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'income' AND tenant_id = ? AND date >= ? AND date < ?",
                     (tenant_id, start_date.isoformat(), end_date.isoformat()))
        total_income = cursor.fetchone()[0]
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'expense' AND tenant_id = ? AND date >= ? AND date < ?",
                     (tenant_id, start_date.isoformat(), end_date.isoformat()))
        total_expenses = cursor.fetchone()[0]
        cursor.execute("SELECT category, SUM(amount) as total FROM transactions WHERE type = 'expense' AND tenant_id = ? AND date >= ? AND date < ? GROUP BY category ORDER BY total DESC",
                     (tenant_id, start_date.isoformat(), end_date.isoformat()))
        expenses_by_category = {}
        for row in cursor.fetchall():
            expenses_by_category[row[0]] = row[1]
        return {
            'year': year, 'month': month,
            'total_income': total_income, 'total_expenses': total_expenses,
            'net_savings': total_income - total_expenses,
            'expenses_by_category': expenses_by_category
        }
    
    def set_budget(self, month: int, year: int, category: str, amount: float, tenant_id: int = 1):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO budgets (tenant_id, month, year, category, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (tenant_id, month, year, category, amount, datetime.now().isoformat()))
        self.conn.commit()
    
    def close(self):
        if self.conn:
            self.conn.close()
