from src.models.encryption import encrypt, decrypt
"""
KwachaKeeper - SQLite Database Manager
Multi-tenant secure database with tenant isolation
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional
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
        
        # Tenants table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Transactions table
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
        
        # Budgets table
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
        
        # Savings goals
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
        
        # Recurring transactions
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
        
        # Create default tenant if none exists
        cursor.execute("SELECT COUNT(*) FROM tenants")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO tenants (name, created_at) VALUES (?, ?)", 
                         ('Default', datetime.now().isoformat()))
        
        self.conn.commit()
    
    def add_transaction(self, transaction: Transaction, tenant_id: int = 1) -> int:
        """Add a new transaction"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (tenant_id, amount, type, category, description, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            tenant_id,
            transaction.amount,
            transaction.transaction_type.value,
            transaction.category.value,
            encrypt(transaction.description),
            transaction.date.isoformat(),
            transaction.created_at.isoformat()
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_transactions(
        self, 
        tenant_id: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transaction_type: Optional[TransactionType] = None,
        category: Optional[Category] = None
    ) -> List[Transaction]:
        """Get transactions with optional filters"""
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
        """Calculate current balance for a tenant"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0)
                as balance
            FROM transactions
            WHERE tenant_id = ?
        """, (tenant_id,))
        result = cursor.fetchone()
        return result[0] if result else 0.0
    
    def get_monthly_summary(self, year: int, month: int, tenant_id: int = 1) -> dict:
        """Get financial summary for a specific month"""
        cursor = self.conn.cursor()
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'income' AND tenant_id = ?
            AND date >= ? AND date < ?
        """, (tenant_id, start_date.isoformat(), end_date.isoformat()))
        total_income = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'expense' AND tenant_id = ?
            AND date >= ? AND date < ?
        """, (tenant_id, start_date.isoformat(), end_date.isoformat()))
        total_expenses = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'expense' AND tenant_id = ?
            AND date >= ? AND date < ?
            GROUP BY category
            ORDER BY total DESC
        """, (tenant_id, start_date.isoformat(), end_date.isoformat()))
        
        expenses_by_category = {}
        for row in cursor.fetchall():
            expenses_by_category[row[0]] = row[1]
        
        return {
            'year': year,
            'month': month,
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net_savings': total_income - total_expenses,
            'expenses_by_category': expenses_by_category
        }
    
    def set_budget(self, month: int, year: int, category: str, amount: float, tenant_id: int = 1):
        """Set or update a budget category"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO budgets (tenant_id, month, year, category, amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (tenant_id, month, year, category, amount, datetime.now().isoformat()))
        self.conn.commit()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
