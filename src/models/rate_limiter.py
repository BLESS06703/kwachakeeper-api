"""
KwachaKeeper - Rate Limiter
Prevents brute force attacks
"""

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests=5, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.attempts = defaultdict(list)
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed. Key can be IP or email."""
        now = time.time()
        self.attempts[key] = [t for t in self.attempts[key] if now - t < self.window_seconds]
        
        if len(self.attempts[key]) >= self.max_requests:
            return False
        
        self.attempts[key].append(now)
        return True
    
    def remaining(self, key: str) -> int:
        """Get remaining attempts"""
        now = time.time()
        self.attempts[key] = [t for t in self.attempts[key] if now - t < self.window_seconds]
        return max(0, self.max_requests - len(self.attempts[key]))
    
    def reset(self, key: str):
        """Reset attempts for a key"""
        self.attempts[key] = []


# Global instance
login_limiter = RateLimiter(max_requests=5, window_seconds=60)
signup_limiter = RateLimiter(max_requests=3, window_seconds=120)
