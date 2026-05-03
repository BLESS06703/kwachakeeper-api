"""
KwachaKeeper - Authentication Database
User management and JWT token handling
"""

import sqlite3
import jwt
import time
from datetime import datetime
from src.models.user import User

JWT_SECRET = "kwacha-keeper-secret-key-change-in-production"
JWT_EXPIRY = 7 * 24 * 60 * 60  # 7 days in seconds


class AuthDatabase:
    """Authentication database manager"""
    
    def __init__(self, db_path: str = "kwacha_keeper.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._initialize_db()
    
    def _initialize_db(self):
        """Create users table if it doesn't exist"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Add user_id to transactions table for multi-user support
        try:
            cursor.execute("ALTER TABLE transactions ADD COLUMN user_id INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        self.conn.commit()
    
    def create_user(self, email: str, password: str) -> User:
        """Create a new user"""
        password_hash, salt = User.hash_password(password)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO users (email, password_hash, salt, created_at)
            VALUES (?, ?, ?, ?)
        ''', (email, password_hash, salt, datetime.now().isoformat()))
        self.conn.commit()
        
        return User(
            id=cursor.lastrowid,
            email=email,
            password_hash=password_hash,
            salt=salt
        )
    
    def get_user_by_email(self, email: str) -> User:
        """Get user by email"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if row:
            return User(
                id=row['id'],
                email=row['email'],
                password_hash=row['password_hash'],
                salt=row['salt'],
                created_at=datetime.fromisoformat(row['created_at'])
            )
        return None
    
    def authenticate(self, email: str, password: str) -> str:
        """Authenticate user and return JWT token"""
        user = self.get_user_by_email(email)
        
        if user and User.verify_password(password, user.salt, user.password_hash):
            return self.generate_token(user)
        return None
    
    def generate_token(self, user: User) -> str:
        """Generate JWT token"""
        payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': int(time.time()) + JWT_EXPIRY
        }
        return jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    
    def verify_token(self, token: str) -> dict:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
