"""Create a throw-away demo database filled with INVENTED data (no personal information).

    python demo_data.py            creates ledger.db with three months of sample data, goals, a loan and a recurring rule
    python demo_data.py --force    replaces an existing ledger.db (be careful: this deletes it)

The demo PIN is  demo1234
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

os.environ["LEDGER_DEMO"] = "1"      # must be set before ledger is imported
import ledger  # noqa: E402

if ledger.DB_PATH.exists():
    if "--force" not in sys.argv:
        sys.exit("ledger.db already exists, so nothing was changed. Use --force only if you are sure you want to delete it.")
    ledger.DB_PATH.unlink()

ledger.setup()                       # tables, categories, starter keywords and the invented history
ledger.set_pin("demo1234")
today = date.today()
with sqlite3.connect(ledger.DB_PATH) as c:
    cat = {n: i for n, i in c.execute("SELECT name, id FROM categories")}
    acc = {n: i for n, i in c.execute("SELECT name, id FROM accounts")}
    c.executemany("INSERT INTO goals (name, target, deadline, accounts) VALUES (?, ?, ?, ?)", [
        ("Emergency fund", 300000, None, "Money Market,Bank"),
        ("Laptop upgrade", 180000, str(today + timedelta(days=240)), "Money Market"),
        ("One million", 1000000, None, "Money Market,Bank,Equity (Stocks)"),
    ])
    c.execute("INSERT INTO recurring (name, type, amount, category_id, account_id, day, start_date, last_date, active) "
              "VALUES ('Home internet', 'Outflow', 3000, ?, ?, ?, ?, ?, 1)",
              (cat["Utilities"], acc["Cash"], (today + timedelta(days=5)).day, str(today - timedelta(days=70)),
               str(today - timedelta(days=25))))
    c.execute("INSERT INTO loans (person, direction, due_date, note) VALUES ('Friend A', 'lent', ?, '')",
              (str(today + timedelta(days=9)),))
    c.execute("INSERT INTO transactions (date, amount, type, account_id, to_account_id, description, loan_id) "
              "VALUES (?, 5000, 'Transfer', ?, ?, 'Lent to Friend A', 1)",
              (str(today - timedelta(days=6)), acc["Cash"], acc["Loans receivable"]))
print("Demo database created. Start the app with:  streamlit run app.py   (PIN: demo1234)")
