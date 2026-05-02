"""
KwachaKeeper - Budget Model
Monthly budget tracking and alerts
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from .transaction import Category, TransactionType


@dataclass
class Budget:
    """Monthly budget model"""
    id: Optional[int]
    month: int  # 1-12
    year: int
    category_budgets: Dict[str, float]  # Category name -> budget amount
    total_budget: float
    created_at: datetime = datetime.now()
    
    def get_remaining(self, category: Category, spent: float) -> float:
        """Calculate remaining budget for category"""
        budgeted = self.category_budgets.get(category.value, 0)
        return budgeted - spent
    
    def get_alert_percentage(self, category: Category, spent: float) -> float:
        """Get percentage of budget used"""
        budgeted = self.category_budgets.get(category.value, 0)
        if budgeted == 0:
            return 0
        return (spent / budgeted) * 100
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'month': self.month,
            'year': self.year,
            'category_budgets': self.category_budgets,
            'total_budget': self.total_budget,
            'created_at': self.created_at.isoformat()
        }