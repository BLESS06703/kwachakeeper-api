"""
KwachaKeeper - Authentication Database
Multi-tenant user management with JWT tokens
"""

import sqlite3
import jwt
import time
from datetime import datetime
from src.models.user import User

JWT_SECRET = "kwacha-keeper-secret-key-change-in-production"
JWT_EXPIRY = 7 * 24 * 60 * 60  # 7 days


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
                tenant_id INTEGER NOT NULL DEFAULT 1,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')
        self.conn.commit()
    
    def create_tenant(self, name: str) -> int:
        """Create a new tenant and return tenant_id"""
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO tenants (name, created_at) VALUES (?, ?)",
                     (name, datetime.now().isoformat()))
        self.conn.commit()
        return cursor.lastrowid
    
    def create_user(self, email: str, password: str, tenant_id: int = None) -> User:
        """Create a new user. If no tenant_id, creates a new tenant."""
        password_hash, salt = User.hash_password(password)
        
        if tenant_id is None:
            tenant_id = self.create_tenant(f"Tenant_{email}")
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO users (tenant_id, email, password_hash, salt, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (tenant_id, email, password_hash, salt, datetime.now().isoformat()))
        self.conn.commit()
        
        return User(
            id=cursor.lastrowid,
            email=email,
            password_hash=password_hash,
            salt=salt,
            tenant_id=tenant_id
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
                tenant_id=row['tenant_id']
            )
        return None
    
    def authenticate(self, email: str, password: str) -> str:
        """Authenticate user and return JWT token with tenant_id"""
        user = self.get_user_by_email(email)
        
        if user and User.verify_password(password, user.salt, user.password_hash):
            return self.generate_token(user)
        return None
    
    def generate_token(self, user: User) -> str:
        """Generate JWT token with tenant_id"""
        payload = {
            'user_id': user.id,
            'tenant_id': user.tenant_id,
            'email': user.email,
            'exp': int(time.time()) + JWT_EXPIRY
        }
        return jwt.encode(payload, JWT_SECRET, algorithm='HS256')
    
    def verify_token(self, token: str) -> dict:
        """Verify JWT token and return payload with tenant_id"""
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
