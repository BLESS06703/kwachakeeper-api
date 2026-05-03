"""
KwachaKeeper - PostgreSQL Database Manager
Persistent storage on Supabase
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import List, Optional
from .transaction import Transaction, TransactionType, Category

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:KwachaSecure2026!@db.aeskkleinhyofnpfqnue.supabase.co:5432/postgres'
)


class Database:
    """PostgreSQL database manager for KwachaKeeper"""
    
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL)
        self.conn.autocommit = True
        self._initialize_db()
    
    def _initialize_db(self):
        """Create tables if they don't exist"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budgets (
                id SERIAL PRIMARY KEY,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(month, year, category)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS savings_goals (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL DEFAULT 0,
                deadline TEXT,
                created_at TEXT NOT NULL
            )
        ''')
    
    def add_transaction(self, transaction: Transaction) -> int:
        """Add a new transaction"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (amount, type, category, description, date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            transaction.amount,
            transaction.transaction_type.value,
            transaction.category.value,
            transaction.description,
            transaction.date.isoformat(),
            transaction.created_at.isoformat()
        ))
        return cursor.fetchone()[0]
    
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
            query += " AND date >= %s"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= %s"
            params.append(end_date.isoformat())
        
        if transaction_type:
            query += " AND type = %s"
            params.append(transaction_type.value)
        
        if category:
            query += " AND category = %s"
            params.append(category.value)
        
        query += " ORDER BY date DESC"
        
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(query, params)
        
        transactions = []
        for row in cursor.fetchall():
            t = Transaction(
                id=row['id'],
                amount=row['amount'],
                transaction_type=TransactionType(row['type']),
                category=Category(row['category']),
                description=row['description'],
                date=datetime.fromisoformat(row['date']),
                created_at=datetime.fromisoformat(row['created_at'])
            )
            transactions.append(t)
        
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
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'income' 
            AND date >= %s AND date < %s
        """, (start_date.isoformat(), end_date.isoformat()))
        total_income = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE type = 'expense' 
            AND date >= %s AND date < %s
        """, (start_date.isoformat(), end_date.isoformat()))
        total_expenses = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE type = 'expense'
            AND date >= %s AND date < %s
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
            INSERT INTO budgets (month, year, category, amount, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (month, year, category)
            DO UPDATE SET amount = EXCLUDED.amount, created_at = EXCLUDED.created_at
        ''', (month, year, category, amount, datetime.now().isoformat()))
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
