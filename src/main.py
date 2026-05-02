#!/usr/bin/env python
"""
KwachaKeeper - Mobile Financial Tracker
Built entirely on Android with Termux + Acode
"""

from datetime import datetime
from src.models.transaction import Transaction, TransactionType, Category
from src.models.database import Database


class KwachaKeeper:
    """Main application class"""
    
    def __init__(self):
        self.db = Database()
        print("💰 KwachaKeeper - Your Mobile Financial Companion")
        print("=" * 50)
    
    def add_income(self, amount: float, category: Category, description: str):
        """Record income"""
        transaction = Transaction(
            id=None,
            amount=amount,
            transaction_type=TransactionType.INCOME,
            category=category,
            description=description,
            date=datetime.now()
        )
        self.db.add_transaction(transaction)
        print(f"✅ Income recorded: +MK{amount:,.2f}")
    
    def add_expense(self, amount: float, category: Category, description: str):
        """Record expense"""
        balance = self.db.get_balance()
        if amount > balance and category != Category.EMERGENCY:
            print(f"⚠️  Warning: Expense exceeds current balance (MK{balance:,.2f})")
        
        transaction = Transaction(
            id=None,
            amount=amount,
            transaction_type=TransactionType.EXPENSE,
            category=category,
            description=description,
            date=datetime.now()
        )
        self.db.add_transaction(transaction)
        print(f"📝 Expense recorded: -MK{amount:,.2f}")
    
    def show_balance(self):
        """Display current balance"""
        balance = self.db.get_balance()
        print(f"\n💵 Current Balance: MK{balance:,.2f}")
        
        # Quick stats
        now = datetime.now()
        summary = self.db.get_monthly_summary(now.year, now.month)
        print(f"\n📊 This Month:")
        print(f"   Income:  MK{summary['total_income']:,.2f}")
        print(f"   Expenses: MK{summary['total_expenses']:,.2f}")
        print(f"   Saved:   MK{summary['net_savings']:,.2f}")
    
    def show_recent_transactions(self, limit: int = 10):
        """Show recent transactions"""
        transactions = self.db.get_transactions()[:limit]
        print(f"\n📋 Recent Transactions:")
        print("-" * 50)
        for t in transactions:
            print(str(t))
    
    def add_budget(self, category: Category, amount: float):
        """Set monthly budget for category"""
        now = datetime.now()
        self.db.set_budget(now.month, now.year, category.value, amount)
        print(f"✅ Budget set: MK{amount:,.2f} for {category.value}")
    
    def check_budget_alerts(self):
        """Check for budget warnings"""
        now = datetime.now()
        status = self.db.get_budget_status(now.year, now.month)
        
        print(f"\n⚠️  Budget Alerts for {now.strftime('%B %Y')}:")
        print("-" * 50)
        
        has_alerts = False
        for category, data in status.items():
            if data['percentage_used'] > 80:
                has_alerts = True
                alert = "🔴 OVER" if data['percentage_used'] >= 100 else "🟡 WARNING"
                print(f"{alert} {category}: MK{data['spent']:,.2f} of MK{data['budgeted']:,.2f} ({data['percentage_used']:.0f}%)")
        
        if not has_alerts:
            print("✅ All budgets on track!")
    
    def run(self):
        """Main application loop"""
        while True:
            print("\n" + "=" * 50)
            print("1. Add Income")
            print("2. Add Expense")
            print("3. View Balance")
            print("4. Recent Transactions")
            print("5. Set Budget")
            print("6. Budget Alerts")
            print("7. Exit")
            
            choice = input("\nChoose option (1-7): ").strip()
            
            if choice == "1":
                print("\nIncome Categories:")
                income_cats = [c for c in Category if c.value in [
                    "Salary/Wages", "Business Income", "Remittance/Foreign", "Side Hustle"
                ]]
                for i, cat in enumerate(income_cats, 1):
                    print(f"{i}. {cat.value}")
                
                cat_choice = int(input("Category: ")) - 1
                amount = float(input("Amount (MK): "))
                desc = input("Description: ")
                self.add_income(amount, income_cats[cat_choice], desc)
            
            elif choice == "2":
                print("\nExpense Categories:")
                expense_cats = [c for c in Category if c.value in [
                    "Food & Groceries", "Transport (Minibus/Fuel)", 
                    "Airtime & Data", "Utilities (ESCOM/Water)",
                    "Rent/Housing", "Education/School Fees",
                    "Healthcare/Medicine", "Family Support"
                ]]
                for i, cat in enumerate(expense_cats, 1):
                    print(f"{i}. {cat.value}")
                
                cat_choice = int(input("Category: ")) - 1
                amount = float(input("Amount (MK): "))
                desc = input("Description: ")
                self.add_expense(amount, expense_cats[cat_choice], desc)
            
            elif choice == "3":
                self.show_balance()
            
            elif choice == "4":
                self.show_recent_transactions()
            
            elif choice == "5":
                print("\nSet Budget Category:")
                for i, cat in enumerate(Category, 1):
                    print(f"{i}. {cat.value}")
                cat_choice = int(input("Category: ")) - 1
                amount = float(input("Monthly Budget (MK): "))
                self.add_budget(list(Category)[cat_choice], amount)
            
            elif choice == "6":
                self.check_budget_alerts()
            
            elif choice == "7":
                print("\n👋 Thank you for using KwachaKeeper!")
                self.db.close()
                break


if __name__ == "__main__":
    app = KwachaKeeper()
    
    # Demo data for testing
    print("📱 Adding demo transactions...")
    app.add_income(150000, Category.SALARY, "Monthly Salary - January")
    app.add_expense(25000, Category.FOOD, "Groceries at Shoprite")
    app.add_expense(15000, Category.TRANSPORT, "Minibus fare - monthly")
    app.add_expense(10000, Category.AIRTIME, "TNM Data bundle")
    app.add_expense(35000, Category.RENT, "House rent")
    app.add_expense(5000, Category.UTILITIES, "ESCOM electricity")
    
    app.show_balance()
    app.run()