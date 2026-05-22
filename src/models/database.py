"""
KwachaKeeper - SQLite Database Manager
Lightweight, works perfectly on Android/Termux
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional
from .transaction import Transaction, TransactionType, Category


class Database:
    """SQLite database manager for KwachaKeeper"""
    
    def __init__(self, db_path: str = "kwacha_keeper.db"):
        """Initialize database connection"""
        self.db_path = db_path
        self.conn = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Create tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Budgets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(month, year, category)
            )
        ''')
        
        # Savings goals
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Recurring transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                frequency TEXT NOT NULL DEFAULT 'monthly',
                next_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        self.conn.commit()
    
    def add_transaction(self, transaction: Transaction) -> int:
        """Add a new transaction"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (amount, type, category, description, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            transaction.amount,
            transaction.transaction_type.value,
            transaction.category.value,
            transaction.description,
            transaction.date.isoformat(),
            transaction.created_at.isoformat()
        ))
        # Recurring transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                frequency TEXT NOT NULL DEFAULT 'monthly',
                next_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        self.conn.commit()
        return cursor.lastrowid
    
    def get_transactions(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transaction_type: Optional[TransactionType] = None,
        category: Optional[Category] = None
    ) -> List[Transaction]:
        """Get transactions with optional filters"""
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        
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
            transactions.append(Transaction.from_dict(dict(row)))
        
        return transactions
    
    def get_balance(self) -> float:
        """Calculate current balance"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0)
                as balance
            FROM transactions
        """)
        
        result = cursor.fetchone()
        return result[0] if result else 0.0
    
    def get_monthly_summary(self, year: int, month: int) -> dict:
        """Get financial summary for a specific month"""
        cursor = self.conn.cursor()
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Income total
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'income' 
            AND date >= ? AND date < ?
        """, (start_date.isoformat(), end_date.isoformat()))
        total_income = cursor.fetchone()[0]
        
        # Expense total
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'expense' 
            AND date >= ? AND date < ?
        """, (start_date.isoformat(), end_date.isoformat()))
        total_expenses = cursor.fetchone()[0]
        
        # By category
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'expense'
            AND date >= ? AND date < ?
            GROUP BY category
            ORDER BY total DESC
        """, (start_date.isoformat(), end_date.isoformat()))
        
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
    
    def set_budget(self, month: int, year: int, category: str, amount: float):
        """Set or update a budget category"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO budgets (month, year, category, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (month, year, category, amount, datetime.now().isoformat()))
        # Recurring transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recurring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                frequency TEXT NOT NULL DEFAULT 'monthly',
                next_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        self.conn.commit()
    
    def get_budget_status(self, year: int, month: int) -> dict:
        """Get budget vs actual spending"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT category, amount FROM budgets
            WHERE month = ? AND year = ?
        """, (month, year))
        
        budgets = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get actual spending
        summary = self.get_monthly_summary(year, month)
        
        budget_status = {}
        for category, budgeted in budgets.items():
            spent = summary['expenses_by_category'].get(category, 0)
            budget_status[category] = {
                'budgeted': budgeted,
                'spent': spent,
                'remaining': budgeted - spent,
                'percentage_used': (spent / budgeted * 100) if budgeted > 0 else 0
            }
        
        return budget_status
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()