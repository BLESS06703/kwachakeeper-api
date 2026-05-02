"""
KwachaKeeper - Transaction Model
Handles all financial transaction data
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class TransactionType(Enum):
    """Types of financial transactions"""
    INCOME = "income"
    EXPENSE = "expense"
    SAVINGS = "savings"
    INVESTMENT = "investment"


class Category(Enum):
    """Localized categories for Malawi"""
    # Income Categories
    SALARY = "Salary/Wages"
    BUSINESS = "Business Income"
    REMITTANCE = "Remittance/Foreign"
    SIDE_HUSTLE = "Side Hustle"
    
    # Expense Categories
    FOOD = "Food & Groceries"
    TRANSPORT = "Transport (Minibus/Fuel)"
    AIRTIME = "Airtime & Data"
    UTILITIES = "Utilities (ESCOM/Water)"
    RENT = "Rent/Housing"
    EDUCATION = "Education/School Fees"
    HEALTH = "Healthcare/Medicine"
    FAMILY = "Family Support"
    
    # Savings Categories
    EMERGENCY = "Emergency Fund"
    GOAL = "Specific Goal"
    INVESTMENT = "Investment"


@dataclass
class Transaction:
    """Core transaction model"""
    id: Optional[int]
    amount: float
    transaction_type: TransactionType
    category: Category
    description: str
    date: datetime
    created_at: datetime = datetime.now()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'amount': self.amount,
            'type': self.transaction_type.value,
            'category': self.category.value,
            'description': self.description,
            'date': self.date.isoformat(),
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        """Create transaction from dictionary"""
        return cls(
            id=data.get('id'),
            amount=data['amount'],
            transaction_type=TransactionType(data['type']),
            category=Category(data['category']),
            description=data['description'],
            date=datetime.fromisoformat(data['date']),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat()))
        )
    
    def is_large_transaction(self, threshold: float = 100000) -> bool:
        """Check if transaction exceeds threshold (for alerts)"""
        return self.amount > threshold
    
    def get_vat_amount(self, vat_rate: float = 0.165) -> float:
        """Calculate VAT (16.5% in Malawi)"""
        if self.transaction_type == TransactionType.INCOME:
            return self.amount * vat_rate
        return 0.0
    
    def get_font_awesome_icon(self) -> str:
        """Get Font Awesome icon class for transaction category"""
        icons = {
            # Income
            "Salary/Wages": "fa-solid fa-briefcase",
            "Business Income": "fa-solid fa-store",
            "Remittance/Foreign": "fa-solid fa-money-bill-transfer",
            "Side Hustle": "fa-solid fa-lightbulb",
            # Expenses
            "Food & Groceries": "fa-solid fa-cart-shopping",
            "Transport (Minibus/Fuel)": "fa-solid fa-bus",
            "Airtime & Data": "fa-solid fa-mobile-screen",
            "Utilities (ESCOM/Water)": "fa-solid fa-bolt",
            "Rent/Housing": "fa-solid fa-house",
            "Education/School Fees": "fa-solid fa-graduation-cap",
            "Healthcare/Medicine": "fa-solid fa-hospital",
            "Family Support": "fa-solid fa-people-roof",
            # Savings
            "Emergency Fund": "fa-solid fa-triangle-exclamation",
            "Specific Goal": "fa-solid fa-bullseye",
            "Investment": "fa-solid fa-chart-line"
        }
        return icons.get(self.category.value, "fa-solid fa-circle-dollar")
    
    def get_category_color(self) -> str:
        """Get color class for category (Tailwind)"""
        colors = {
            # Income - Green shades
            "Salary/Wages": "text-green-600 bg-green-50",
            "Business Income": "text-emerald-600 bg-emerald-50",
            "Remittance/Foreign": "text-teal-600 bg-teal-50",
            "Side Hustle": "text-lime-600 bg-lime-50",
            # Expenses - Red/Orange shades
            "Food & Groceries": "text-orange-600 bg-orange-50",
            "Transport (Minibus/Fuel)": "text-amber-600 bg-amber-50",
            "Airtime & Data": "text-yellow-600 bg-yellow-50",
            "Utilities (ESCOM/Water)": "text-red-600 bg-red-50",
            "Rent/Housing": "text-rose-600 bg-rose-50",
            "Education/School Fees": "text-blue-600 bg-blue-50",
            "Healthcare/Medicine": "text-pink-600 bg-pink-50",
            "Family Support": "text-purple-600 bg-purple-50",
            # Savings - Blue/Indigo shades
            "Emergency Fund": "text-red-700 bg-red-100",
            "Specific Goal": "text-indigo-600 bg-indigo-50",
            "Investment": "text-violet-600 bg-violet-50"
        }
        return colors.get(self.category.value, "text-gray-600 bg-gray-50")
    
    def format_for_sms(self) -> str:
        """Format transaction for SMS notification"""
        sign = "+" if self.transaction_type == TransactionType.INCOME else "-"
        return f"{sign}MK{self.amount:,.2f}\n{self.description}\n{self.category.value}"
    
    def __str__(self) -> str:
        sign = "+" if self.transaction_type == TransactionType.INCOME else "-"
        return f"{sign}MK{self.amount:,.2f} - {self.description} ({self.category.value})"
    
    def __repr__(self) -> str:
        return f"Transaction(amount={self.amount}, type={self.transaction_type.value}, category={self.category.value})"