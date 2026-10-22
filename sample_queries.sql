-- Explore the ledger with SQL (SQLite). Open ledger.db in DB Browser for SQLite, or run these with Python's sqlite3.
-- The data model: accounts, categories, transactions (type = Inflow / Outflow / Transfer), budgets, goals, loans, recurring.

-- 1. Money in and money out per month (transfers between your own accounts are not income or spending)
SELECT substr(date, 1, 7) AS month,
       ROUND(SUM(CASE WHEN type = 'Inflow'  THEN amount END), 2) AS money_in,
       ROUND(SUM(CASE WHEN type = 'Outflow' THEN amount END), 2) AS money_out
FROM transactions
GROUP BY month
ORDER BY month;

-- 2. Spending by category for one month, largest first
SELECT c.name AS category, ROUND(SUM(t.amount), 2) AS spent
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.type = 'Outflow' AND substr(t.date, 1, 7) = (SELECT MAX(substr(date, 1, 7)) FROM transactions)
GROUP BY c.name
ORDER BY spent DESC;

-- 3. Current balance of every account: opening balance + inflows - outflows - transfers out + transfers in
SELECT a.name,
       ROUND(a.opening_balance
         + COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id = a.id AND type = 'Inflow'), 0)
         - COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id = a.id AND type = 'Outflow'), 0)
         - COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id = a.id AND type = 'Transfer'), 0)
         + COALESCE((SELECT SUM(amount) FROM transactions WHERE to_account_id = a.id AND type = 'Transfer'), 0), 2) AS balance
FROM accounts a;

-- 4. Share of income that was saved each month (savings rate)
SELECT substr(date, 1, 7) AS month,
       ROUND(100.0 * (SUM(CASE WHEN type = 'Inflow' THEN amount ELSE 0 END)
                    - SUM(CASE WHEN type = 'Outflow' THEN amount ELSE 0 END))
                    / SUM(CASE WHEN type = 'Inflow' THEN amount END), 1) AS savings_rate_pct
FROM transactions
GROUP BY month;

-- 5. Spending inside the leisure pool (categories flagged is_leisure = 1), per month
SELECT substr(t.date, 1, 7) AS month, ROUND(SUM(t.amount), 2) AS leisure_spent
FROM transactions t JOIN categories c ON c.id = t.category_id
WHERE t.type = 'Outflow' AND c.is_leisure = 1
GROUP BY month;
