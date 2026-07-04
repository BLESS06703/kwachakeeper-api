"""
KwachaKeeper - User Model
"""

import hashlib
import secrets
from datetime import datetime
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """Core user model"""
    id: Optional[int]
    email: str
    password_hash: str
    salt: str
    tenant_id: int = 1
    created_at: datetime = datetime.now()
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        if salt is None:
            salt = secrets.token_hex(16)
        combined = password + salt
        password_hash = hashlib.sha256(combined.encode()).hexdigest()
        return password_hash, salt
    
    @staticmethod
    def verify_password(password: str, salt: str, stored_hash: str) -> bool:
        combined = password + salt
        computed_hash = hashlib.sha256(combined.encode()).hexdigest()
        return computed_hash == stored_hash
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'email': self.email,
            'tenant_id': self.tenant_id,
            'created_at': self.created_at.isoformat()
        }
