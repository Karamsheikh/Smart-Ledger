"""Database layer for Smart Ledger.

    python ledger.py                    create / upgrade the database (never deletes your data)
    python ledger.py --shift-years 1    move every transaction date forward one year (backup first)
    python ledger.py --reset-pin        forgot the PIN? remove it, then set a new one in the app

The old version of this file DROPPED all tables every time it ran. This one never does.
"""
import calendar
import hashlib
import os
import re
import hmac
import secrets
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "ledger.db"          # always next to this file, whatever folder you launch from
BACKUP_DIR = HERE / "backups"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    opening_balance REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL,                 -- Inflow | Outflow | Transfer
    category_id INTEGER REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),   -- money leaves / arrives here
    to_account_id INTEGER REFERENCES accounts (id),         -- Transfer only: destination
    description TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS budgets (          -- monthly limit per category, as % of that month's income
    category_id INTEGER PRIMARY KEY REFERENCES categories (id),
    pct REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS goals (            -- savings goals; progress = balance of the listed accounts
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    deadline TEXT,                            -- YYYY-MM-DD, or NULL for "no deadline"
    accounts TEXT NOT NULL                    -- comma-separated account names that count toward the goal
);
CREATE TABLE IF NOT EXISTS loans (            -- money you lent or borrowed; the money movements are Transfers
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT NOT NULL,
    direction TEXT NOT NULL,                  -- lent | borrowed
    due_date TEXT,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS balance_checks (   -- history of "I counted my real money" checks
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    expected REAL NOT NULL,
    actual REAL NOT NULL,
    adjusted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS keywords (         -- "if the note contains this word, suggest this category"
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    UNIQUE (keyword, category_id)
);
CREATE TABLE IF NOT EXISTS recurring (        -- monthly rules that add transactions automatically
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,                       -- Inflow | Outflow | Transfer
    amount REAL NOT NULL,
    category_id INTEGER REFERENCES categories (id),
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    to_account_id INTEGER REFERENCES accounts (id),
    day INTEGER NOT NULL,                     -- 1-31; in shorter months it falls on the last day
    start_date TEXT NOT NULL,
    last_date TEXT,                           -- date of the newest entry this rule created
    active INTEGER NOT NULL DEFAULT 1
);
"""

_DEMO = os.environ.get("LEDGER_DEMO") == "1"      # demo_data.py sets this; a normal start gives an empty ledger
# Sample opening balances for the invented demo history. Change them in the app (Data & backup) for real use.
DEFAULT_ACCOUNTS = [("Cash", 18500.0 if _DEMO else 0.0), ("Money Market", 60000.0 if _DEMO else 0.0), ("Bank", 0.0), ("Equity (Stocks)", 0.0)]

DEFAULT_CATEGORIES = [
    ("Salary / Inflow", "Inflow"), ("Freelance", "Inflow"), ("Interest", "Inflow"), ("Allowance", "Inflow"),
    ("Leisure", "Outflow"), ("Utilities", "Outflow"), ("Food & Groceries", "Outflow"),
    ("Uncategorised", "Outflow"),
    ("Equity Investments", "Investment"), ("Money Market", "Investment"),
]

# Loans are tracked with two bookkeeping accounts, so lending/borrowing never looks like spending or income:
# lending moves money Cash -> "Loans receivable" (still yours); borrowing moves "Loans payable" -> Cash.
LOAN_ACCOUNTS = ("Loans receivable", "Loans payable")
EXTRA_CATEGORIES = [("Loan written off", "Outflow"), ("Balance adjustment (shortfall)", "Outflow"),
                    ("Balance adjustment (surplus)", "Inflow")]

# Starter words for smart category suggestions (editable in the app; your own history is learned on top of these).
STARTER_KEYWORDS = {
    "Unhealthy snacks": ["chips", "chocolate", "candy", "coke", "pepsi", "cola", "sprite", "fanta", "soda", "cold drink",
                         "samosa", "pakora", "fries", "burger", "pizza", "kfc", "mcdonalds", "ice cream", "biscuit",
                         "cookies", "nuggets", "shawarma", "foodpanda", "food panda", "snack", "snacks", "energy drink",
                         "red bull", "dessert"],
    "Gaming": ["steam", "playstation", "ps5", "ps4", "xbox", "nintendo", "roblox", "fortnite", "valorant", "pubg", "uc",
               "free fire", "minecraft", "game pass", "gamepass", "epic games", "game", "games", "gaming", "gems",
               "skins", "battle pass"],
    "Transport": ["careem", "uber", "indrive", "yango", "rickshaw", "bus", "metro", "orange line", "petrol", "fuel",
                  "parking", "toll", "ride"],
    "Utilities": ["electricity", "lesco", "wapda", "iesco", "sngpl", "sui gas", "gas", "water", "internet", "wifi",
                  "ptcl", "nayatel", "stormfiber", "jazz", "zong", "ufone", "telenor", "mobile load", "load",
                  "phone bill"],
    "Rent": ["rent", "house rent", "landlord"],
    "Food & Groceries": ["grocery", "groceries", "vegetables", "sabzi", "fruit", "fruits", "milk", "eggs", "chicken",
                         "mutton", "beef", "rice", "atta", "flour", "sugar", "lunch", "dinner", "breakfast"],
    "Study & exam fees": ["exam", "exam fee", "tuition", "fee", "fees", "course", "book", "books", "stationery",
                          "registration"],
    "Health": ["doctor", "medicine", "medicines", "pharmacy", "hospital", "clinic", "dentist", "gym"],
    "Family & gifts": ["gift", "sadaqah", "zakat", "donation", "charity", "birthday"],
    "Allowance": ["allowance", "pocket money", "eidi", "from mum", "from dad"],
    "Salary / Inflow": ["salary", "payroll", "stipend", "wage"],
    "Freelance": ["freelance", "fiverr", "upwork", "client", "project"],
    "Interest": ["interest", "profit", "dividend", "payout"],
}

# Budget categories and starter limits (% of monthly income). Gaming + Unhealthy snacks = the leisure cap.
NEW_CATEGORIES = [(n, "Outflow") for n in (
    "Gaming", "Unhealthy snacks", "Transport", "Study & exam fees", "Rent", "Health", "Family & gifts", "Other")]
# A 50% spending plan (so 50% or more is saved). Rent and fees start at 0% until you actually pay them.
DEFAULT_BUDGETS = {
    "Utilities": 6, "Rent": 0, "Food & Groceries": 14, "Transport": 7, "Study & exam fees": 0,
    "Health": 3, "Family & gifts": 4, "Gaming": 6, "Unhealthy snacks": 4, "Other": 6,
}
OLD_DEFAULT_BUDGETS = {   # the first starter limits (after the Utilities rename); only replaced if you never edited them
    "Utilities": 8, "Food & Groceries": 12, "Transport": 6, "Study & exam fees": 12,
    "Health": 3, "Family & gifts": 4, "Gaming": 6, "Unhealthy snacks": 4, "Other": 5,
}

# Invented demo data (no real person): three months relative to today, so the dashboard always looks current.
OTHER = "Uncategorised"


def _sample_history(today):
    rows = []
    for back in (2, 1, 0):
        y, m = today.year, today.month - back
        while m < 1:
            m, y = m + 12, y - 1

        def d(day, y=y, m=m):
            return min(date(y, m, day), today).isoformat()
        i = 2 - back
        rows += [
            (d(1), 90000.0, "Inflow", "Salary / Inflow", "Cash", None, "Salary"),
            (d(3), 12000.0, "Outflow", "Rent", "Cash", None, "Shared flat rent"),
            (d(5), 4500.0, "Outflow", "Utilities", "Cash", None, "Electricity and internet"),
            (d(8), 5500.0, "Outflow", "Food & Groceries", "Cash", None, "Groceries"),
            (d(15), 5500.0, "Outflow", "Food & Groceries", "Cash", None, "Groceries"),
            (d(10), 3500.0, "Outflow", "Transport", "Cash", None, "Fuel and rides"),
            (d(12), [3200.0, 2400.0, 5200.0][i], "Outflow", "Gaming", "Cash", None, "Game purchases"),
            (d(14), [2100.0, 1800.0, 4300.0][i], "Outflow", "Unhealthy snacks", "Cash", None, "Takeaway and snacks"),
            (d(20), 2500.0, "Outflow", "Family & gifts", "Cash", None, "Family"),
            (d(28) if back else d(12), [42000.0, 60000.0, 48000.0][i], "Transfer", None, "Cash", "Money Market", "Monthly saving"),
        ]
        if back == 2:
            rows.append((d(18), 9000.0, "Outflow", "Study & exam fees", "Cash", None, "Course fee"))
        if back == 1:
            rows += [(d(9), 12000.0, "Inflow", "Freelance", "Cash", None, "Freelance project"),
                     (d(22), 1800.0, "Outflow", "Health", "Cash", None, "Pharmacy")]
    return rows


HISTORY = _sample_history(date.today()) if _DEMO else []   # date, amount, type, category, account, to_account, description
LEGACY = set()                            # (only used by a one-off migration in the private edition)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def backup(tag="manual", keep=40):
    """Consistent copy of the database into ./backups (oldest beyond `keep` are pruned)."""
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"ledger_{datetime.now():%Y%m%d_%H%M%S}_{tag}.db"
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    for old in sorted(BACKUP_DIR.glob("ledger_*.db"))[:-keep]:
        old.unlink()
    return dest


def _ids(conn, table):
    return {name: i for i, name in conn.execute(f"SELECT id, name FROM {table}")}


def _insert_history(conn):
    conn.executemany("INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?)", DEFAULT_CATEGORIES + NEW_CATEGORIES)
    acc, cat = _ids(conn, "accounts"), _ids(conn, "categories")
    conn.executemany(
        "INSERT INTO transactions (date, amount, type, category_id, account_id, to_account_id, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(d, amt, t, cat.get(c), acc[a], acc.get(to), desc) for d, amt, t, c, a, to, desc in HISTORY],
    )


def _legacy_ids(conn):
    rows = conn.execute("SELECT id, description, amount FROM transactions").fetchall()
    found = {(d, a): i for i, d, a in rows if (d, a) in LEGACY}
    return list(found.values()) if len(found) == len(LEGACY) else []


def _clamp_history_dates(conn):
    """The imported 'surplus to Money Market' transfers were dated at month end. After a year shift, the current
    month's one can land in the future, which makes balances disagree. Pull any such date back to today."""
    today = str(date.today())
    return conn.execute("UPDATE transactions SET date = ? WHERE date > ? "
                        "AND description LIKE '% surplus to Money Market (from Excel closing split)'",
                        (today, today)).rowcount


def setup():
    """Create tables if missing and upgrade an old database safely. Returns a list of notes."""
    notes, existed = [], DB_PATH.exists()
    with connect() as conn:
        conn.executescript(SCHEMA)
        tx_cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)")}
        has_to_col, has_loan_col = "to_account_id" in tx_cols, "loan_id" in tx_cols
        fresh = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
        legacy = [] if fresh else _legacy_ids(conn)
        legacy_types = conn.execute("SELECT COUNT(*) FROM transactions WHERE type = 'Investment'").fetchone()[0]

    if existed and not fresh and (not has_to_col or legacy):
        notes.append(f"Backup saved: {backup('premigration').name}")

    with connect() as conn:
        if not has_to_col:
            conn.execute("ALTER TABLE transactions ADD COLUMN to_account_id INTEGER REFERENCES accounts (id)")
            notes.append("Added transfer support (to_account_id column).")
        if not has_loan_col:
            conn.execute("ALTER TABLE transactions ADD COLUMN loan_id INTEGER REFERENCES loans (id)")
        if fresh:
            conn.executemany("INSERT INTO accounts (name, opening_balance) VALUES (?, ?)", DEFAULT_ACCOUNTS)
            _insert_history(conn)
            notes.append("New database created with sample data.")
        elif legacy:
            conn.executemany("DELETE FROM transactions WHERE id = ?", [(i,) for i in legacy])
            _insert_history(conn)
            if conn.execute("SELECT SUM(ABS(opening_balance)) FROM accounts").fetchone()[0] == 0:
                conn.executemany("UPDATE accounts SET opening_balance = ? WHERE name = ?",
                                 [(b, n) for n, b in DEFAULT_ACCOUNTS])
            notes.append("Converted the 8 original seed rows into itemised entries + transfers "
                         "(all Excel totals and balances unchanged).")
        elif legacy_types:
            notes.append(f"{legacy_types} old 'Investment' row(s) were left alone because your data differs "
                         "from the original seed. The app ignores them; re-enter them as Transfers.")
    with connect() as conn:
        done = conn.execute("SELECT 1 FROM settings WHERE key = 'budgets_seeded'").fetchone()
        has_data = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0
    if has_data and not done:
        if existed:
            notes.append(f"Backup saved: {backup('prebudgets').name}")
        with connect() as conn:
            conn.executemany("INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?)", NEW_CATEGORIES)
            cat = _ids(conn, "categories")
            conn.executemany("INSERT OR IGNORE INTO budgets (category_id, pct) VALUES (?, ?)",
                             [(cat[n], p) for n, p in DEFAULT_BUDGETS.items() if n in cat])
            conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             [("budget_start", f"{date.today():%Y-%m}"), ("planned_income", "0"),
                              ("budgets_seeded", "1")])
        notes.append("Added budget categories (Gaming, Unhealthy snacks, Transport, ...) with starter limits. "
                     "Edit them in the Budgets tab.")
    with connect() as conn:
        done2 = conn.execute("SELECT 1 FROM settings WHERE key = 'features_v2'").fetchone()
        has_data = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0
    if has_data and not done2:
        with connect() as conn:
            conn.executemany("INSERT OR IGNORE INTO accounts (name, opening_balance) VALUES (?, 0)",
                             [(n,) for n in LOAN_ACCOUNTS])
            conn.executemany("INSERT OR IGNORE INTO categories (name, type) VALUES (?, ?)", EXTRA_CATEGORIES)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('features_v2', '1')")
        notes.append("Added loan accounts and balance-adjustment categories.")
    with connect() as conn:
        moved = _clamp_history_dates(conn)
    if moved:
        notes.append(f"Moved {moved} imported transfer(s) from a future date to today so balances match reality.")
    with connect() as conn:
        done3 = conn.execute("SELECT 1 FROM settings WHERE key = 'features_v3'").fetchone()
        has_data = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0
    if has_data and not done3:
        with connect() as conn:
            cat = _ids(conn, "categories")
            conn.executemany("INSERT OR IGNORE INTO keywords (keyword, category_id) VALUES (?, ?)",
                             [(w, cat[c]) for c, words in STARTER_KEYWORDS.items() if c in cat for w in words])
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('features_v3', '1')")
        notes.append("Added starter keywords for smart category suggestions.")
    with connect() as conn:
        done4 = conn.execute("SELECT 1 FROM settings WHERE key = 'features_v4'").fetchone()
        has_data = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0
    if has_data and not done4:
        if existed:
            notes.append(f"Backup saved: {backup('prebudgetplan').name}")
        with connect() as conn:
            names = _ids(conn, "categories")
            renamed = "Utilities & Rent" in names and "Utilities" not in names
            if renamed:
                conn.execute("UPDATE categories SET name = 'Utilities' WHERE name = 'Utilities & Rent'")
            conn.execute("INSERT OR IGNORE INTO categories (name, type) VALUES ('Rent', 'Outflow')")
            if "is_leisure" not in {r[1] for r in conn.execute("PRAGMA table_info(categories)")}:
                conn.execute("ALTER TABLE categories ADD COLUMN is_leisure INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE categories SET is_leisure = 1 WHERE name IN ('Gaming', 'Unhealthy snacks', 'Leisure')")
            cat = _ids(conn, "categories")
            conn.execute("UPDATE OR IGNORE keywords SET category_id = ? WHERE keyword = 'rent'", (cat["Rent"],))
            current = dict(conn.execute("SELECT c.name, b.pct FROM budgets b JOIN categories c ON c.id = b.category_id"))
            if current == OLD_DEFAULT_BUDGETS:
                conn.executemany("INSERT OR REPLACE INTO budgets (category_id, pct) VALUES (?, ?)",
                                 [(cat[n], p) for n, p in DEFAULT_BUDGETS.items()])
                notes.append("Limits updated to a 50% spending plan. Rent and Study & exam fees start at 0% until you pay them.")
            elif current != DEFAULT_BUDGETS:
                notes.append("Kept your own budget limits. Open Budgets > Edit limits to fit them into 50%.")
            conn.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                             [("save_min", "50"), ("save_stretch", "60")])
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('features_v4', '1')")
            notes.append("Split 'Utilities & Rent' into Utilities and Rent." if renamed else "Added the leisure flag on categories.")
    with connect() as conn:
        done5 = conn.execute("SELECT 1 FROM settings WHERE key = 'features_v5'").fetchone()
        has_data = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] > 0
    if has_data and not done5:
        with connect() as conn:
            total = conn.execute("SELECT COALESCE(SUM(b.pct), 0) FROM budgets b JOIN categories c ON c.id = b.category_id "
                                 "WHERE c.is_leisure = 1").fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('leisure_pct', ?)",
                         (str(round(total, 1) if total > 0 else 10),))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('features_v5', '1')")
        notes.append("Budget simplified: one shared leisure pool, and one pool for everything else.")
    for n in notes:
        print("[ledger]", n)
    return notes


# ----------------------------------------------------------------------------- smart helpers (no database)
_STOP = {"the", "and", "for", "with", "from", "paid", "pay", "payment", "bill", "recurring", "lent", "borrowed",
         "repaid", "written", "off", "balance", "check", "ledger", "counted", "pkr"}


def tokens(text):
    return [w for w in re.findall(r"[a-z]+", str(text).lower()) if len(w) >= 3 and w not in _STOP]


def learn(rows):
    """rows: (note, category, type). Returns {word: Counter({(category, type): times})} from your own entries."""
    seen = defaultdict(Counter)
    for note, category, kind in rows:
        for w in set(tokens(note)):
            seen[w][(category, kind)] += 1
    return seen


def suggest(text, kind, keywords, learned):
    """Suggest a category for a note. keywords: [(word, category, type)]. Returns (category or None, reason)."""
    padded = " " + " ".join(re.findall(r"[a-z0-9]+", str(text).lower())) + " "
    if not padded.strip():
        return None, ""
    hits = [(padded.find(f" {w.lower()} "), -len(w), w, c) for w, c, t in keywords
            if t == kind and f" {w.lower()} " in padded]
    if hits:                                   # the word that comes first in your note wins; longer phrase breaks ties
        _, _, word, category = min(hits)
        return category, f"the word '{word}'"
    score = Counter()
    for w in set(tokens(text)):
        counts = {c: v for (c, t), v in learned.get(w, {}).items() if t == kind}
        total = sum(counts.values())
        for c, v in counts.items():
            score[c] += v / total
    if score:
        category, s = score.most_common(1)[0]
        if s >= 0.5:
            return category, "what you usually pick for these words"
    return None, ""


def upcoming_dates(day, start, last, today, end):
    """Dates after `today` up to and including `end` on which a monthly rule will fire."""
    out = []
    for y, m in _months(today, end):
        d = _occurrence(day, y, m)
        if today < d <= end and d >= start and (last is None or d > last):
            out.append(d)
    return out


def project(start, monthly, annual_return=0.0, yearly_raise=0.0, target=None, max_months=1200):
    """Month-by-month balances (first entry = today). Saving grows by `yearly_raise` every 12 months."""
    i = (1 + annual_return) ** (1 / 12) - 1
    bal, pay, path = start, monthly, [start]
    for m in range(1, max_months + 1):
        if m > 1 and (m - 1) % 12 == 0:
            pay *= 1 + yearly_raise
        bal = bal * (1 + i) + pay
        path.append(bal)
        if target is not None and bal >= target:
            break
    return path


def months_to_reach(start, target, monthly, annual_return=0.0, yearly_raise=0.0, max_months=1200):
    if start >= target:
        return 0
    path = project(start, monthly, annual_return, yearly_raise, target, max_months)
    return len(path) - 1 if path[-1] >= target else None


def needed_saving(start, target, months, annual_return=0.0, yearly_raise=0.0):
    """Starting monthly saving needed to reach `target` in `months` months."""
    if start >= target:
        return 0.0
    lo, hi = 0.0, max(target, 1.0)
    for _ in range(60):
        mid = (lo + hi) / 2
        if project(start, mid, annual_return, yearly_raise, None, months)[-1] >= target:
            hi = mid
        else:
            lo = mid
    return hi


def _occurrence(day, y, m):
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def _months(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def due_dates(day, start, last, today):
    """Dates on or before `today` at which a rule should have fired but has not yet."""
    return [d for y, m in _months(start, today)
            if start <= (d := _occurrence(day, y, m)) <= today and (last is None or d > last)]


def next_due(day, start, last, today):
    """The next date after `today` on which the rule will fire."""
    y, m = today.year, today.month
    for _ in range(26):
        d = _occurrence(day, y, m)
        if d > today and d >= start and (last is None or d > last):
            return d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def run_recurring(today=None):
    """Create every transaction that is due (also fills in months the app was closed). Safe to call often."""
    today, made = today or date.today(), 0
    with connect() as conn:
        rules = conn.execute("SELECT id, name, type, amount, category_id, account_id, to_account_id, day, "
                             "start_date, last_date FROM recurring WHERE active = 1").fetchall()
        for rid, name, typ, amt, cat, acc, to, day, start, last in rules:
            due = due_dates(day, date.fromisoformat(start), date.fromisoformat(last) if last else None, today)
            for d in due:
                conn.execute("INSERT INTO transactions (date, amount, type, category_id, account_id, to_account_id, "
                             "description) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (str(d), amt, typ, cat, acc, to, f"Recurring: {name}"))
            if due:
                conn.execute("UPDATE recurring SET last_date = ? WHERE id = ?", (str(due[-1]), rid))
                made += len(due)
    return made


def get_setting(key, default=""):
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def detect_dropbox():
    p = Path.home() / "Dropbox"
    return str(p / "Smart ledger backups") if p.is_dir() else ""


def copy_offsite(src, folder, name):
    """Copy a backup file to an off-PC folder (for example Dropbox) and keep only the newest 60 there."""
    folder = Path(folder)
    if not folder.is_dir():
        if folder.parent.is_dir():
            folder.mkdir()
        else:
            raise OSError(f"folder not found: {folder}")
    dest = folder / name
    shutil.copy2(src, dest)
    for old in sorted(folder.glob("ledger_*.db"))[:-60]:
        old.unlink()
    return dest


def auto_backup(today=None):
    """Once a day (the first time the app is opened): back up locally and copy to the off-PC folder if one is set.
    Returns a status line the first time it runs that day, otherwise None."""
    today = str(today or date.today())
    if get_setting("last_auto_backup") == today:
        return None
    local = backup("daily", keep=40)
    status, folder = "saved on this PC only (no off-PC folder set)", get_setting("backup_dir")
    if folder:
        try:
            copy_offsite(local, folder, f"ledger_{today}.db")
            monthly = Path(folder) / "monthly"                     # one copy per month, kept forever (never pruned)
            if not (monthly / f"ledger_{today[:7]}.db").exists():
                monthly.mkdir(exist_ok=True)
                shutil.copy2(local, monthly / f"ledger_{today[:7]}.db")
            status = f"copied to {folder}"
        except OSError as e:
            status = f"FAILED to copy to {folder} ({e})"
    set_setting("last_auto_backup", today)
    set_setting("last_backup_status", f"{today}: {status}")
    return status


KEEP_ON_RESTORE = ("pin_salt", "pin_hash", "pin_fails", "pin_locked_until", "backup_dir",
                   "last_auto_backup", "last_backup_status")


def list_backups():
    folders = [BACKUP_DIR] + ([Path(get_setting("backup_dir"))] if get_setting("backup_dir") else [])
    return sorted((p for f in folders if f.is_dir() for p in [*f.glob("ledger_*.db"), *f.glob("monthly/ledger_*.db")]),
                  key=lambda p: p.name, reverse=True)


def restore_backup(path):
    """Replace the live database with a backup. A safety copy of the current data is made first, and your PIN and
    backup-folder setting are kept. Returns the safety copy's path."""
    src = sqlite3.connect(path)
    try:
        ok = src.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError:
        ok, tables = False, set()
    finally:
        src.close()
    if not ok or not {"accounts", "categories", "transactions"} <= tables:
        raise ValueError("That file doesn't look like a valid ledger backup.")
    keep = {k: get_setting(k) for k in KEEP_ON_RESTORE}
    safety = backup("prerestore", keep=60)
    src, dst = sqlite3.connect(path), sqlite3.connect(DB_PATH)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    setup()
    for k, v in keep.items():
        if v:
            set_setting(k, v)
    return safety


MAX_TRIES = 5            # wrong PINs allowed before a lock-out
LOCK_SECONDS = 600       # length of the lock-out (10 minutes), shared by every device


def _hash_pin(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def has_pin():
    with connect() as conn:
        return conn.execute("SELECT 1 FROM settings WHERE key = 'pin_hash'").fetchone() is not None


def set_pin(pin):
    """Store a salted scrypt hash of the PIN (the PIN itself is never saved)."""
    salt = secrets.token_bytes(16)
    with connect() as conn:
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         [("pin_salt", salt.hex()), ("pin_hash", _hash_pin(pin, salt).hex()),
                          ("pin_fails", "0"), ("pin_locked_until", "0")])


def check_pin(pin):
    """Return (ok, message). Repeated wrong guesses lock every device out for LOCK_SECONDS."""
    now = time.time()
    with connect() as conn:
        s = dict(conn.execute("SELECT key, value FROM settings WHERE key LIKE 'pin\\_%' ESCAPE '\\'").fetchall())
        if "pin_hash" not in s:
            return True, ""
        locked = float(s.get("pin_locked_until", 0))
        if now < locked:
            return False, f"Too many wrong attempts. Try again in about {int((locked - now) // 60) + 1} minute(s)."
        good = hmac.compare_digest(_hash_pin(pin, bytes.fromhex(s["pin_salt"])).hex(), s["pin_hash"])
        fails = 0 if good else int(s.get("pin_fails", 0)) + 1
        until = now + LOCK_SECONDS if fails >= MAX_TRIES else 0
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                         [("pin_fails", str(0 if until else fails)), ("pin_locked_until", str(until))])
    if good:
        return True, ""
    if until:
        return False, f"Wrong PIN. Locked for {LOCK_SECONDS // 60} minutes."
    return False, f"Wrong PIN. {MAX_TRIES - fails} attempt(s) left before a {LOCK_SECONDS // 60}-minute lock."


def reset_pin():
    with connect() as conn:
        conn.execute("DELETE FROM settings WHERE key LIKE 'pin\\_%' ESCAPE '\\'")


def shift_years(n):
    backup("shift_years")
    with connect() as conn:
        conn.execute("UPDATE transactions SET date = date(date, ?)", (f"{n:+d} years",))
        _clamp_history_dates(conn)
    print(f"[ledger] All dates moved {n:+d} year(s).")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--reset-pin":
        setup()
        reset_pin()
        print("[ledger] PIN removed. The app will ask you to set a new one the next time it opens.")
    elif len(sys.argv) == 3 and sys.argv[1] == "--shift-years":
        setup()
        shift_years(int(sys.argv[2]))
    else:
        setup()
        print("[ledger] Database is ready.")
