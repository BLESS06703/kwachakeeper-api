# KwachaKeeper API

Python backend for the KwachaKeeper financial tracking application. Built entirely on Android with Termux.

## Tech Stack

- Python 3
- SQLite database
- Custom HTTP server (no frameworks)
- Deployed on Render

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health check |
| GET | `/api/balance` | Current account balance |
| GET | `/api/summary` | Monthly income and expenses |
| GET | `/api/transactions` | List all transactions |
| POST | `/api/transactions` | Create a new transaction |
| DELETE | `/api/transactions/:id` | Delete a transaction |
| GET | `/api/budgets` | Get monthly budgets |
| POST | `/api/budgets` | Set a budget category |

## Local Setup

```bash
cd KwachaKeeper
pip install -r requirements.txt
python api_server.py
