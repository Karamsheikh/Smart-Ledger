"""Smart Ledger - personal finance tracker (Streamlit + SQLite). Run: streamlit run app.py"""
import socket
import time
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import exporter
import ledger
import theme

IDLE_LOCK_MIN = 30              # the ledger locks itself after this many minutes without a click
CURRENCY = "Rs"                 # change to "$", "AED", ... (the old version hard-coded "$")
OLD_LEISURE = "Leisure"                            # a general leisure category, flagged as leisure in the database
HIDE_FROM_LIMITS = [OLD_LEISURE, "Uncategorised"]
SYSTEM_CATS = {"Uncategorised", "Loan written off",       # created by the app, not for typing in by hand
               "Balance adjustment (shortfall)", "Balance adjustment (surplus)"}
TYPES = ["Inflow", "Outflow", "Transfer"]

st.set_page_config(page_title="Smart Ledger", page_icon="📒", layout="wide")
theme.inject(st)


def ensure_theme_config():
    """Write .streamlit/config.toml once, so native widgets (radios, tabs, tables) use the same colours."""
    cfg = Path(__file__).resolve().parent / ".streamlit" / "config.toml"
    if cfg.exists():
        return
    try:
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text('[theme]\nbase = "dark"\nprimaryColor = "#D9A441"\nbackgroundColor = "#0A1F1B"\n'
                       'secondaryBackgroundColor = "#0E2823"\ntextColor = "#EFEBDD"\nfont = "sans serif"\n\n'
                       '[client]\ntoolbarMode = "minimal"\n\n[browser]\ngatherUsageStats = false\n')
    except OSError:
        pass


ensure_theme_config()
_v = tuple(int(x) for x in st.__version__.split(".")[:2])
WIDE = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}


def show_chart(fig, height=300, legend=True):
    st.plotly_chart(theme.style_fig(fig, height, legend), config={"displayModeBar": False}, **WIDE)


def fmt(x):
    return f"{'-' if x < 0 else ''}{CURRENCY} {abs(x):,.2f}"


def signed(x):
    return f"{'+' if x >= 0 else ''}{fmt(x)}"


@st.cache_resource
def _startup():
    return ledger.setup()      # creates / safely upgrades the database once per app start


_startup()


def q(sql, params=()):
    with ledger.connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def run(sql, params=()):
    with ledger.connect() as conn:
        conn.execute(sql, params)


def flash(msg, icon="✅"):
    st.session_state["flash"] = (msg, icon)


if "flash" in st.session_state:
    _m, _i = st.session_state.pop("flash")
    st.toast(_m, icon=_i)



def login_gate():
    """Nothing below this runs until the right PIN has been entered."""
    now = time.time()
    if not ledger.has_pin():
        st.markdown(theme.login_head("Set a PIN", "This ledger holds your money records, and anyone on your Wi-Fi can open "
                                     "its link. Choose a PIN or password of at least 6 characters. You'll need it each "
                                     "time you open the app."), unsafe_allow_html=True)
        with st.form("set_pin"):
            p1 = st.text_input("New PIN / password", type="password")
            p2 = st.text_input("Repeat it", type="password")
            if st.form_submit_button("Save PIN"):
                if len(p1) < 6:
                    st.error("Use at least 6 characters.")
                elif p1 != p2:
                    st.error("The two entries don't match.")
                else:
                    ledger.set_pin(p1)
                    st.session_state.update(auth_ok=True, last_seen=now)
                    st.rerun()
        st.stop()
    if st.session_state.get("auth_ok"):
        if now - st.session_state.get("last_seen", 0) < IDLE_LOCK_MIN * 60:
            st.session_state["last_seen"] = now
            return
        st.session_state.update(auth_ok=False, idle_locked=True)
    st.markdown(theme.login_head("Locked", "Enter your PIN to open your accounts."), unsafe_allow_html=True)
    if st.session_state.pop("idle_locked", False):
        st.markdown(theme.notice("warn", f"Locked after {IDLE_LOCK_MIN} minutes without activity."), unsafe_allow_html=True)
    with st.form("login"):
        pin = st.text_input("PIN / password", type="password")
        if st.form_submit_button("Unlock"):
            ok, msg = ledger.check_pin(pin)
            if ok:
                st.session_state.update(auth_ok=True, last_seen=now)
                st.rerun()
            st.error(msg)
    st.stop()


login_gate()

made = ledger.run_recurring()                       # add any recurring entries that have come due
if made:
    st.toast(f"{made} recurring entr{'y' if made == 1 else 'ies'} added.", icon="🔁")
_bk = ledger.auto_backup()                          # once a day: local backup + off-PC copy if a folder is set
if _bk and _bk.startswith("FAILED"):
    st.toast("Today's off-PC backup failed. Open Data & backup to check the folder.", icon="⚠️")

# ----------------------------------------------------------------------------- data
accounts = q("SELECT id, name, opening_balance FROM accounts ORDER BY id")
cats = q("SELECT id, name, type, is_leisure FROM categories ORDER BY type, name")
tx = q("""
    SELECT t.id, t.date, t.type, t.amount, t.description, t.category_id, c.name AS category,
           t.account_id, a.name AS account, t.to_account_id, b.name AS to_account, t.loan_id
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN accounts a ON a.id = t.account_id
    LEFT JOIN accounts b ON b.id = t.to_account_id
    ORDER BY t.date, t.id""")
tx["date"] = pd.to_datetime(tx["date"])
tx["month"] = tx["date"].dt.to_period("M")
acc_names = accounts["name"].tolist()
LOAN_ACCOUNTS = list(ledger.LOAN_ACCOUNTS)
pick_accounts = [x for x in acc_names if x not in LOAN_ACCOUNTS]     # accounts offered in everyday forms
acc_id = dict(zip(accounts["name"], accounts["id"]))
cat_id = dict(zip(cats["name"], cats["id"]))


def entry_cats(kind, keep=None):
    """Categories offered when typing a new entry. System ones only appear if the entry already uses them."""
    return [n for n in cats.loc[cats["type"] == kind, "name"] if n not in SYSTEM_CATS or n == keep]
unknown = tx[~tx["type"].isin(TYPES)]


def get_setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key = ?", (key,))
    return r["value"].iloc[0] if not r.empty else default


def set_setting(key, value):
    run("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)))


budgets = q("SELECT c.name AS category, b.pct FROM budgets b JOIN categories c ON c.id = b.category_id")
pct = dict(zip(budgets["category"], budgets["pct"].astype(float)))
total_pct = sum(pct.values())
save_min = float(get_setting("save_min", "50") or 50)          # you plan to save at least this % of income
save_stretch = float(get_setting("save_stretch", "60") or 60)  # and hope to reach this
leisure_pct = float(get_setting("leisure_pct", "10") or 10)    # one shared pool for all leisure categories
leisure_cats = cats.loc[cats["is_leisure"] == 1, "name"].tolist()
goals = q("SELECT id, name, target, deadline, accounts FROM goals ORDER BY id")
loans = q("SELECT id, person, direction, due_date, note FROM loans ORDER BY id")
checks = q("""SELECT bc.date, a.name AS account, bc.expected, bc.actual, bc.adjusted
              FROM balance_checks bc JOIN accounts a ON a.id = bc.account_id ORDER BY bc.id DESC""")
rules = q("""SELECT r.id, r.name, r.type, r.amount, r.day, r.start_date, r.last_date, r.active,
                    c.name AS category, a.name AS account, b.name AS to_account
             FROM recurring r
             LEFT JOIN categories c ON c.id = r.category_id
             LEFT JOIN accounts a ON a.id = r.account_id
             LEFT JOIN accounts b ON b.id = r.to_account_id ORDER BY r.id""")


def balances(upto=None):
    """Balance of every account after all transactions dated on or before `upto`."""
    t = tx if upto is None else tx[tx["date"] <= upto]
    bal = accounts.set_index("name")["opening_balance"].astype(float)
    sign = t["type"].map({"Inflow": 1, "Outflow": -1, "Transfer": -1}).fillna(0)
    bal = bal.add((t["amount"] * sign).groupby(t["account"]).sum(), fill_value=0)
    moved_in = t[t["type"] == "Transfer"].groupby("to_account")["amount"].sum()
    return bal.add(moved_in, fill_value=0).reindex(acc_names)


cur_month = pd.Period(date.today(), "M")
months = (pd.period_range(tx["month"].min(), max(tx["month"].max(), cur_month), freq="M")
          if not tx.empty else [cur_month])

rows = []
for m in months:
    mt = tx[tx["month"] == m]
    inflow = mt.loc[mt["type"] == "Inflow", "amount"].sum()
    outflow = mt.loc[mt["type"] == "Outflow", "amount"].sum()
    closing = balances(m.end_time)
    rows.append({"Month": str(m), "Opening": balances(m.start_time - pd.Timedelta(days=1)).sum(),
                 "Inflows": inflow, "Outflows": outflow, "Closing": closing.sum(), **closing.round(2).to_dict()})
summary = pd.DataFrame(rows).round(2)
bal_now = balances(pd.Timestamp(date.today()))          # what you have today (future-dated entries excluded)
VISIBLE = [x for x in acc_names if x not in LOAN_ACCOUNTS or summary[x].abs().sum() > 0]
RECV, PAY = LOAN_ACCOUNTS
t_day = date.today()

kw_rows = q("SELECT k.id, k.keyword, c.name AS category, c.type FROM keywords k "
            "JOIN categories c ON c.id = k.category_id ORDER BY k.keyword")
keywords = list(zip(kw_rows["keyword"], kw_rows["category"], kw_rows["type"]))
SKIP_LEARN = set(HIDE_FROM_LIMITS) | {"Other", "Loan written off", "Balance adjustment (shortfall)",
                                      "Balance adjustment (surplus)"}
SKIP_NOTE = ("Recurring:", "Balance check", "Lent to", "Borrowed from", "Repaid", "Written off", "Oct ", "Sep ")
usable = tx[tx["type"].isin(["Inflow", "Outflow"]) & tx["description"].apply(lambda s: isinstance(s, str) and bool(s))
            & tx["category"].notna() & ~tx["category"].isin(SKIP_LEARN)
            & ~tx["description"].fillna("").str.startswith(SKIP_NOTE)]
learned = ledger.learn(zip(usable["description"], usable["category"], usable["type"]))


def suggest(text, kind):
    return ledger.suggest(text, kind, keywords, learned)

def loan_parts(row):
    t = tx[tx["loan_id"] == row.id]
    if row.direction == "lent":
        given = t.loc[t["to_account"] == RECV, "amount"].sum()
        back = t.loc[(t["type"] == "Transfer") & (t["account"] == RECV), "amount"].sum()
        return given, back, t.loc[(t["type"] == "Outflow") & (t["account"] == RECV), "amount"].sum()
    return (t.loc[(t["type"] == "Transfer") & (t["account"] == PAY), "amount"].sum(),
            t.loc[t["to_account"] == PAY, "amount"].sum(), 0.0)

loan_rows = []
for ln_ in loans.itertuples():
    given, back, written = loan_parts(ln_)
    left_ = given - back - written
    due = pd.to_datetime(ln_.due_date).date() if pd.notna(ln_.due_date) and ln_.due_date else None
    loan_rows.append({"id": ln_.id, "Person": ln_.person, "Type": "You lent" if ln_.direction == "lent" else "You borrowed",
                      "Original": given, "Paid back": back, "Written off": written, "Outstanding": left_,
                      "Due": due.isoformat() if due else "",
                      "Status": "Settled" if left_ < 0.005 else ("Overdue" if due and due < t_day else "Open"),
                      "Note": ln_.note or ""})
owed_to_me = sum(r["Outstanding"] for r in loan_rows if r["Type"] == "You lent")
i_owe = sum(r["Outstanding"] for r in loan_rows if r["Type"] == "You borrowed")
overdue_rows = [r for r in loan_rows if r["Status"] == "Overdue"]

# ----------------------------------------------------------------------------- sidebar
def quick_add_ui():
    """Big, simple entry screen for the phone. Suggests a category from what you type."""
    ss = st.session_state
    ss.setdefault("qa_type", "Outflow")
    ss.setdefault("qa_amount", 0.0)
    ss.setdefault("qa_notes", "")
    ss.setdefault("qa_why", "")
    ss.setdefault("qa_acc", "Cash" if "Cash" in pick_accounts else pick_accounts[0])
    cat_opts = entry_cats(ss["qa_type"])
    if ss.get("qa_cat") not in cat_opts:
        ss["qa_cat"] = cat_opts[0] if cat_opts else None
    acc_label = lambda n: f"{n} ({fmt(bal_now[n])})"                                   # noqa: E731

    def on_type():
        ss["qa_cat"], ss["qa_why"] = None, ""

    def on_notes():
        found, why = suggest(ss["qa_notes"], ss["qa_type"])
        ss["qa_why"] = why if found else ""
        if found:
            ss["qa_cat"] = found

    def use_pick(p):
        ss["qa_type"], ss["qa_amount"], ss["qa_notes"] = p["type"], float(p["amount"]), p["desc"]
        ss["qa_cat"], ss["qa_acc"], ss["qa_why"] = p["category"], p["account"], "your usual entry"

    def save_quick():
        amt, typ, cat, acc = ss["qa_amount"], ss["qa_type"], ss.get("qa_cat"), ss["qa_acc"]
        ss["qa_err"] = ""
        if amt <= 0:
            ss["qa_err"] = "Enter an amount."
        elif not cat:
            ss["qa_err"] = "Pick a category."
        else:
            run("INSERT INTO transactions (date, amount, type, category_id, account_id, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(ss.get("qa_date", date.today())), amt, typ, cat_id[cat], acc_id[acc], ss["qa_notes"].strip()))
            low = typ == "Outflow" and bal_now[acc] - amt < 0
            flash(f"Saved {fmt(amt)} to {cat}." + (f" {acc} is now below zero." if low else ""), "⚠️" if low else "✅")
            ss["qa_amount"], ss["qa_notes"], ss["qa_why"] = 0.0, "", ""

    st.markdown("<style>div[data-testid='stNumberInput'] input{font-size:1.6rem}"
                "div.stButton>button{min-height:3rem;font-size:1.1rem}</style>", unsafe_allow_html=True)
    st.radio("Type", ["Outflow", "Inflow"], horizontal=True, key="qa_type", on_change=on_type)
    st.number_input("Amount", min_value=0.0, step=50.0, format="%.2f", key="qa_amount")
    st.text_input("What was it?", key="qa_notes", on_change=on_notes, placeholder="e.g. foodpanda burger")
    st.selectbox("Category", cat_opts, key="qa_cat")
    if ss["qa_why"]:
        st.caption(f"Suggested from {ss['qa_why']}.")
    st.selectbox("Account", pick_accounts, key="qa_acc", format_func=acc_label)
    with st.expander("Change the date"):
        st.date_input("Date", value=date.today(), key="qa_date")
    if ss.get("qa_err"):
        st.error(ss["qa_err"])
    st.button("Save", type="primary", on_click=save_quick, use_container_width=True, key="qa_save")

    recent = tx[tx["type"].isin(["Inflow", "Outflow"]) & (tx["date"] >= pd.Timestamp(date.today()) - pd.Timedelta(days=120))
                & tx["description"].apply(lambda s: isinstance(s, str) and bool(s))
                & ~tx["description"].fillna("").str.startswith(SKIP_NOTE) & tx["category"].notna()]
    if not recent.empty:
        grp = (recent.sort_values("date").groupby(["description", "type", "category", "account"])
               .agg(n=("id", "count"), amount=("amount", "last"), last=("date", "max")).reset_index()
               .sort_values(["n", "last"], ascending=False).head(6))
        st.caption("Your usual ones (tap to fill in):")
        cols = st.columns(2)
        for i, r in enumerate(grp.itertuples()):
            cols[i % 2].button(f"{r.description} · {r.amount:,.0f}", key=f"qa_pick_{i}", on_click=use_pick,
                               args=({"type": r.type, "amount": r.amount, "desc": r.description,
                                      "category": r.category, "account": r.account},))


def query_mode():
    try:
        return st.query_params.get("mode")
    except AttributeError:
        return (st.experimental_get_query_params().get("mode") or [None])[0]


if query_mode() == "quick":
    st.markdown(theme.masthead("Quick add"), unsafe_allow_html=True)
    quick_add_ui()
    st.markdown('<a href="./" target="_self">Open the full ledger</a>', unsafe_allow_html=True)
    st.stop()

st.sidebar.markdown(theme.brand(), unsafe_allow_html=True)
if st.sidebar.button("Lock now"):
    st.session_state["auth_ok"] = False
    st.rerun()

st.sidebar.markdown("[Phone quick-add page](?mode=quick)")
st.sidebar.header("Month")
month_opts = [str(m) for m in months][::-1]
sel = st.sidebar.selectbox("Month to view", month_opts, label_visibility="collapsed",
                           index=month_opts.index(str(cur_month)) if str(cur_month) in month_opts else 0)
srow = summary[summary["Month"] == sel].iloc[0]

st.sidebar.header("Record transaction")
t_type = st.sidebar.radio("Type", TYPES, horizontal=True)
tx_n = st.session_state.get("tx_form_n", 0)                     # bumped after a save so the form resets
with st.sidebar.form(f"tx_form_{tx_n}"):
    t_date = st.date_input("Date", value=date.today())
    t_amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f")
    label = lambda n: f"{n} ({fmt(bal_now[n])})"          # noqa: E731  (shows live balance)
    if t_type == "Transfer":
        acc_from = st.selectbox("From account", pick_accounts, format_func=label)
        acc_to = st.selectbox("To account", pick_accounts, index=min(1, len(pick_accounts) - 1), format_func=label)
        t_cat = None
    else:
        t_cat = st.selectbox("Category", entry_cats(t_type))
        acc_from, acc_to = st.selectbox("Account", pick_accounts, format_func=label), None
    t_desc = st.text_input("Notes")
    if st.form_submit_button("Save transaction"):
        if t_amount <= 0:
            st.error("Amount must be greater than zero.")
        elif t_type == "Transfer" and acc_from == acc_to:
            st.error("Pick two different accounts.")
        elif t_type != "Transfer" and t_cat is None:
            st.error("Add a category for this type first.")
        else:
            run("INSERT INTO transactions (date, amount, type, category_id, account_id, to_account_id, description)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(t_date), t_amount, t_type, cat_id.get(t_cat), acc_id[acc_from], acc_id.get(acc_to), t_desc))
            st.session_state["tx_form_n"] = tx_n + 1
            if t_type != "Inflow" and bal_now[acc_from] - t_amount < 0:
                flash(f"Saved - but {acc_from} is now below zero.", "⚠️")
            else:
                flash("Transaction saved.")
            st.rerun()

with st.sidebar.expander("Add category"):
    new_type = st.radio("Type", ["Outflow", "Inflow"], horizontal=True, key="newcat_type",
                        help="Outflow = something you spend on. Inflow = money coming in.")
    cat_n = st.session_state.get("cat_form_n", 0)                 # bumped after a save so the form resets
    with st.form(f"cat_form_{cat_n}"):
        new_name = st.text_input("Category name")
        if new_type == "Outflow":
            new_leis = st.radio("Is it a leisure category?", ["- choose -", "Yes, leisure", "No, not leisure"],
                                help="Leisure categories share one monthly pool (your 'wants'). Everything else is a need.")
        else:
            new_leis = None
        if st.form_submit_button("Create category"):
            if not new_name.strip():
                st.error("Enter a name.")
            elif new_name.strip() in cat_id:
                st.error("That category already exists.")
            elif new_type == "Outflow" and new_leis == "- choose -":
                st.error("Please say whether this is a leisure category.")
            else:
                is_l = int(new_type == "Outflow" and new_leis.startswith("Yes"))
                run("INSERT INTO categories (name, type, is_leisure) VALUES (?, ?, ?)", (new_name.strip(), new_type, is_l))
                st.session_state["cat_form_n"] = cat_n + 1
                flash(f"Category '{new_name.strip()}' added" + (" as leisure." if is_l else "."))
                st.rerun()

# ----------------------------------------------------------------------------- main
st.markdown(theme.masthead(pd.Period(sel).strftime("%B %Y")), unsafe_allow_html=True)
if not unknown.empty:
    st.warning(f"{len(unknown)} transaction(s) have an old type ('Investment') and are ignored in balances. "
               "Delete them in the Manage tab and re-enter them as Transfers.")

tab_dash, tab_quick, tab_tx, tab_bud, tab_goal, tab_rec, tab_loan, tab_review, tab_manage, tab_data = st.tabs(
    ["Dashboard", "Quick add", "Transactions", "Budgets", "Savings goals", "Recurring", "Loans", "Review", "Manage", "Data & backup"])

with tab_dash:
    sel_p = pd.Period(sel)
    month_change = srow["Closing"] - srow["Opening"]
    net = srow["Inflows"] - srow["Outflows"]
    rate_txt = f"{net / srow['Inflows']:.0%}" if srow["Inflows"] else "n/a"
    prev_label = (sel_p - 1).end_time.strftime("%d %B %Y")
    sub_html = (f"<b class='{'in' if month_change >= 0 else 'out'}'>{'+' if month_change >= 0 else '&minus;'}"
                f"{theme.plain(abs(month_change))}</b> since {prev_label}")
    st.markdown(theme.hero(f"Net worth at the end of {sel_p.strftime('%B %Y')}", srow["Closing"], sub_html,
                           theme.sparkline(summary["Closing"].tolist()[-12:],
                                           [pd.Period(m).strftime("%b %y") for m in summary["Month"].tolist()[-12:]])),
                unsafe_allow_html=True)
    st.markdown(theme.strip([
        ("Money in", theme.figure(srow["Inflows"]), sel_p.strftime("%B"), "in"),
        ("Money out", theme.figure(srow["Outflows"]), sel_p.strftime("%B"), "out"),
        ("Saved", theme.figure(net), "Money in minus money out", "in" if net >= 0 else "out"),
        ("Savings rate", f"{rate_txt}", f"Plan: at least {save_min:.0f}%, stretch {save_stretch:.0f}%",
         "in" if srow["Inflows"] and net / srow["Inflows"] * 100 >= save_min else "brass"),
    ]), unsafe_allow_html=True)

    left_col, right_col = st.columns([1, 1], gap="large")
    with left_col:
        st.subheader("Where your money is")
        sub_names = {LOAN_ACCOUNTS[0]: "Money you have lent", LOAN_ACCOUNTS[1]: "Money you owe"}
        st.markdown(theme.account_rows([(x, sub_names.get(x, ""), float(srow[x])) for x in VISIBLE], float(srow["Closing"])),
                    unsafe_allow_html=True)
    with right_col:
        st.subheader("Coming up")
        win = st.radio("Look ahead", [7, 14, 30], index=1, horizontal=True, key="upc_win",
                       format_func=lambda d: f"{d} days", label_visibility="collapsed")
        t0, t1 = date.today(), date.today() + timedelta(days=win)
        coming, proj = [], bal_now.copy()
        for r_ in rules.itertuples():
            if not r_.active:
                continue
            last_ = date.fromisoformat(r_.last_date) if pd.notna(r_.last_date) and r_.last_date else None
            for d_ in ledger.upcoming_dates(int(r_.day), date.fromisoformat(r_.start_date), last_, t0, t1):
                coming.append((d_, r_.name, "Recurring " + r_.type.lower(), r_.amount,
                               {"Inflow": "in", "Outflow": "out"}.get(r_.type, "")))
                if r_.type == "Inflow":
                    proj[r_.account] += r_.amount
                elif r_.type == "Outflow":
                    proj[r_.account] -= r_.amount
                else:
                    proj[r_.account] -= r_.amount
                    proj[r_.to_account] += r_.amount
        for ln_ in loan_rows:
            if ln_["Outstanding"] >= 0.005 and ln_["Due"] and ln_["Due"] <= t1.isoformat():
                owed = ln_["Type"] == "You lent"
                coming.append((date.fromisoformat(ln_["Due"]), f"{ln_['Person']} " + ("owes you" if owed else "is owed by you"),
                               "Loan, overdue" if ln_["Status"] == "Overdue" else "Loan",
                               ln_["Outstanding"], "in" if owed else "out"))
        for g_ in goals.itertuples():
            if pd.notna(g_.deadline) and g_.deadline:
                dl_ = pd.to_datetime(g_.deadline).date()
                accs_ = [x for x in str(g_.accounts).split(",") if x in acc_names]
                left_ = g_.target - (float(bal_now[accs_].sum()) if accs_ else 0.0)
                if t0 <= dl_ <= t0 + timedelta(days=max(win, 30)) and left_ > 0:
                    coming.append((dl_, f"{g_.name} deadline", "Goal", left_, ""))
        coming.sort(key=lambda c: c[0])
        if coming:
            st.markdown(theme.coming_rows([
                (d.strftime("%d %b"), "overdue" if d < t0 else "today" if d == t0 else f"in {(d - t0).days} days",
                 title, kind, amt, tone) for d, title, kind, amt, tone in coming]), unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='empty'>Nothing scheduled in the next {win} days.</div>", unsafe_allow_html=True)
        for acc_n in pick_accounts:
            if proj[acc_n] < 0 <= bal_now[acc_n] and proj[acc_n] != bal_now[acc_n]:
                st.markdown(theme.notice("warn", f"{acc_n} would drop to {fmt(proj[acc_n])} after your scheduled entries. "
                                                 "Move money in first, or adjust the rule."), unsafe_allow_html=True)

    st.subheader("Month by month")
    show = summary[["Month", "Opening", "Inflows", "Outflows", "Closing"] + VISIBLE].iloc[::-1]
    st.dataframe(show.style.format({c: "{:,.2f}" for c in show.columns if c != "Month"}),
                 hide_index=True, **WIDE)

    col_a, col_b = st.columns([1.15, 1], gap="large")
    with col_a:
        st.subheader("Money in and out")
        trend = summary.melt("Month", ["Inflows", "Outflows"], "Metric", "Amount")
        fig = px.bar(trend, x="Month", y="Amount", color="Metric", barmode="group",
                     color_discrete_map={"Inflows": theme.MINT, "Outflows": theme.CORAL})
        fig.update_xaxes(type="category", title_text="")
        show_chart(fig, 330)
    with col_b:
        st.subheader("Where it went")
        out = tx[(tx["month"] == sel_p) & (tx["type"] == "Outflow")].groupby("category")["amount"].sum().sort_values(ascending=False)
        if out.empty:
            st.markdown("<div class='empty'>No spending recorded this month.</div>", unsafe_allow_html=True)
        else:
            li, ni, colors = 0, 0, []
            for c_ in out.index:
                if c_ in leisure_cats:
                    colors.append(theme.LEISURE_SHADES[li % len(theme.LEISURE_SHADES)]); li += 1
                elif c_ in SYSTEM_CATS:
                    colors.append(theme.NEUTRAL)
                else:
                    colors.append(theme.NEEDS_SHADES[ni % len(theme.NEEDS_SHADES)]); ni += 1
            fig = px.pie(out.reset_index(), names="category", values="amount", hole=0.64)
            fig.update_traces(marker=dict(colors=colors, line=dict(color=theme.BOTTLE, width=2)), textinfo="none", sort=False,
                              hovertemplate="%{label}<br>Rs %{value:,.2f} (%{percent})<extra></extra>")
            fig.update_layout(legend=dict(orientation="h", x=0, y=-0.08, yanchor="top", font=dict(size=12, color=theme.IVORY)),
                              annotations=[dict(text=f"<span style='font-size:11px'>Spent</span><br><b style='font-size:18px;"
                                                     f"font-family:Newsreader,Georgia,serif'>{theme.plain(float(out.sum()))}</b>",
                                                x=0.5, y=0.5, showarrow=False, font=dict(color=theme.IVORY))])
            show_chart(fig, 380, True)
            st.caption("Brass shades are leisure; green and blue shades are everything else.")

with tab_quick:
    quick_add_ui()

with tab_tx:
    f1, f2 = st.columns([1, 2])
    kinds = f1.multiselect("Type", TYPES, default=TYPES)
    needle = f2.text_input("Search notes / category / account").strip().lower()
    view = tx[(tx["month"] == pd.Period(sel)) & (tx["type"].isin(kinds))].copy()
    if needle:
        hay = (view["description"].fillna("") + " " + view["category"].fillna("") + " "
               + view["account"].fillna("") + " " + view["to_account"].fillna("")).str.lower()
        view = view[hay.str.contains(needle, regex=False)]
    view = view.sort_values(["date", "id"])
    view["date"] = view["date"].dt.date
    view.insert(0, "no", range(1, len(view) + 1))                  # 1, 2, 3 ... in date order; the database id stays hidden
    newest_first = st.checkbox("Newest first", value=False, key="tx_newest")
    shown_tx = view[["no", "date", "type", "category", "account", "to_account", "amount", "description"]]
    st.dataframe((shown_tx.iloc[::-1] if newest_first else shown_tx).rename(columns=str.title).rename(columns={"No": "No.", "To_Account": "To account"}),
                 column_config={"Amount": st.column_config.NumberColumn(format="%.2f")}, hide_index=True, **WIDE)
    st.caption(f"{len(view)} transaction(s) in {sel}.")

with tab_bud:
    planned = float(get_setting("planned_income", "0") or 0)
    basis = max(srow["Inflows"], planned) if pd.Period(sel) == cur_month else srow["Inflows"]
    needs_pct = 100 - save_min - leisure_pct
    out_m = tx[(tx["month"] == pd.Period(sel)) & (tx["type"] == "Outflow")]
    by_cat = out_m.groupby("category")["amount"].sum()
    leis_spent = float(by_cat[by_cat.index.isin(leisure_cats)].sum())
    needs_spent = float(by_cat.sum() - leis_spent)
    leis_limit, needs_limit = leisure_pct / 100 * basis, needs_pct / 100 * basis
    save_target = save_min / 100 * basis
    saved = srow["Inflows"] - srow["Outflows"]

    st.markdown(f"<div class='note' style='margin:.2rem 0 .4rem'>For every Rs 100 you receive in {pd.Period(sel).strftime('%B')}: "
                f"save at least {save_min:.0f} (stretch {save_stretch:.0f}), spend up to {leisure_pct:.0f} on leisure and up to "
                f"{needs_pct:.0f} on everything else. Income used: {fmt(basis)}.</div>", unsafe_allow_html=True)
    if basis == 0:
        st.markdown(theme.notice("warn", "No income recorded for this month yet, so every pool is zero. Record your income, "
                                         "or set 'Expected monthly income' under Your plan below."), unsafe_allow_html=True)

    leis_over = leis_spent > leis_limit + 0.005
    needs_over = needs_spent > needs_limit + 0.005
    save_ratio = (saved / save_target) if save_target > 0 else 0.0
    save_tone = "ok" if saved >= save_target and save_target > 0 else "warn"
    save_card = (f"<div class='pool'><div class='cap'>Savings, at least {save_min:.0f}%</div>"
                 f"<div class='big'>{theme.figure(saved)}</div><div class='of'>of {fmt(save_target)} target</div>"
                 f"<div class='meter'><i class='{save_tone}' style='width:{min(max(save_ratio, 0), 1) * 100:.0f}%'></i></div>"
                 f"<div class='status {'in' if save_tone == 'ok' else 'brass'}'>"
                 f"{(fmt(saved - save_target) + ' above target') if saved >= save_target else (fmt(save_target - saved) + ' to go')}</div></div>")
    st.markdown(theme.pools([save_card,
                             theme.pool(f"Leisure pool, {leisure_pct:.0f}%", leis_spent, leis_limit),
                             theme.pool(f"Everything else, {needs_pct:.0f}%", needs_spent, needs_limit)]), unsafe_allow_html=True)
    if leis_over:
        st.markdown(theme.notice("bad", f"Leisure is over its pool by {fmt(leis_spent - leis_limit)}."), unsafe_allow_html=True)
    if needs_over:
        st.markdown(theme.notice("bad", f"Everything else is over its pool by {fmt(needs_spent - needs_limit)}."), unsafe_allow_html=True)
    if not leis_over and not needs_over and basis > 0:
        st.markdown(theme.notice("ok", "Both spending pools are within their limits."), unsafe_allow_html=True)

    st.subheader("Where it went")
    total_out = float(by_cat.sum())
    ordered = sorted(by_cat.items(), key=lambda kv: (kv[0] not in leisure_cats, -kv[1]))
    st.markdown(theme.bar_rows([("Leisure (earlier entries)" if c == OLD_LEISURE else c, "Leisure" if c in leisure_cats and c != OLD_LEISURE else "",
                                 float(v), v / total_out * 100,
                                 "leis" if c in leisure_cats else "need") for c, v in ordered],
                               "No spending recorded for this month."), unsafe_allow_html=True)

    st.subheader("Your plan")
    out_choices = entry_cats("Outflow")
    with st.form("plan_form"):
        p1, p2, p3 = st.columns(3)
        n_min = p1.number_input("Save at least (% of income)", min_value=0.0, max_value=100.0, value=save_min, step=5.0)
        n_str = p2.number_input("Stretch savings goal (%)", min_value=0.0, max_value=100.0, value=save_stretch, step=5.0)
        n_leis = p3.number_input("Leisure pool (% of income)", min_value=0.0, max_value=100.0, value=leisure_pct, step=1.0)
        chosen = st.multiselect("Which categories are leisure? (they share the leisure pool)", out_choices,
                                default=[c for c in out_choices if c in leisure_cats])
        planned_in = st.number_input("Expected monthly income (optional)", min_value=0.0, value=planned, step=500.0,
                                     help="This month's pools use whichever is higher: this figure or the income "
                                          "recorded so far. Useful before payday.")
        st.caption("Everything that isn't leisure counts as 'everything else' and shares what's left after savings and "
                   "leisure. That includes rent and fees when you start paying them.")
        if st.form_submit_button("Save plan"):
            if n_str < n_min:
                st.error("The stretch goal must be at least the minimum.")
            elif n_min + n_leis > 100:
                st.error(f"Savings {n_min:.0f}% plus leisure {n_leis:.0f}% is more than 100%.")
            else:
                for c_name in out_choices:
                    run("UPDATE categories SET is_leisure = ? WHERE id = ?", (int(c_name in chosen), cat_id[c_name]))
                set_setting("save_min", n_min)
                set_setting("save_stretch", n_str)
                set_setting("leisure_pct", n_leis)
                set_setting("planned_income", planned_in)
                flash("Plan saved.", "✅")
                st.rerun()

with tab_goal:
    today = date.today()
    recent = summary.tail(3)
    pace = float((recent["Inflows"] - recent["Outflows"]).mean()) if not recent.empty else 0.0
    this = summary[summary["Month"] == str(cur_month)].iloc[0]
    net_now = this["Inflows"] - this["Outflows"]
    plan_save = save_min
    st.markdown(theme.strip([
        ("Net worth today", theme.figure(float(bal_now.sum())), "Shares at cost; money you lent counts, money you owe is subtracted", ""),
        ("Saved this month", theme.figure(net_now), (f"{net_now / this['Inflows']:.0%} of income" if this["Inflows"] else "No income yet"),
         "in" if net_now >= 0 else "out"),
        ("Recent monthly pace", theme.figure(pace), "Average saved over your last 3 months", "brass"),
        ("Savings plan", f"{plan_save:.0f}%", f"At least {plan_save:.0f}%, stretch {save_stretch:.0f}%", ""),
    ]), unsafe_allow_html=True)

    if goals.empty:
        st.markdown("<div class='empty'>No goals yet. Add one below, for example an emergency fund or next year's fees.</div>",
                    unsafe_allow_html=True)
    for g in goals.itertuples():
        accs = [x for x in str(g.accounts).split(",") if x in acc_names]
        saved = float(bal_now[accs].sum()) if accs else 0.0
        left = max(g.target - saved, 0.0)
        done = saved / g.target if g.target > 0 else 0.0
        verdict = ""
        if pd.notna(g.deadline) and g.deadline:
            dl = pd.to_datetime(g.deadline).date()
            months_left = max((dl - today).days / 30.44, 0.0)
            need = left / max(months_left, 1.0)
            if left <= 0:
                verdict = "<span class='in'><b>Goal reached.</b></span>"
            elif dl < today:
                verdict = f"<span class='out'>Deadline passed with {fmt(left)} still to go.</span>"
            else:
                verdict = (f"To finish by {dl.strftime('%d %B %Y')} you need about <b>{fmt(need)} a month</b> "
                           f"(your recent pace is {fmt(pace)}). ")
                verdict += ("<span class='in'><b>On track at your recent pace.</b></span>" if pace >= need else
                            f"<span class='out'><b>Short by about {fmt(need - pace)} a month.</b></span>")
        else:
            if left <= 0:
                verdict = "<span class='in'><b>Goal reached.</b></span>"
            elif pace > 0 and -(-left // pace) > 600:
                verdict = (f"At your recent pace of {fmt(pace)} a month, saving alone would take over 50 years. "
                           "Add a deadline to see the monthly amount you'd need, or split this into smaller milestone goals.")
            elif pace > 0:
                verdict = (f"At your recent pace of {fmt(pace)} a month you'd get there in about "
                           f"<b>{-(-left // pace):.0f} months</b> (around {pd.Period(today, 'M') + int(-(-left // pace))}).")
            else:
                verdict = "Your recent pace is zero or negative, so there's no projection yet."
        st.markdown(theme.goal(g.name, done * 100, saved, g.target, left,
                               ", ".join(accs) or "no accounts", verdict), unsafe_allow_html=True)

    if not goals.empty:
        st.subheader("Progress over time")
        gname = (goals["name"].iloc[0] if len(goals) == 1
                 else st.selectbox("Goal to chart", goals["name"].tolist(), key="goal_chart"))
        gsel = goals[goals["name"] == gname].iloc[0]
        gacc = [x for x in str(gsel["accounts"]).split(",") if x in acc_names]
        hist = pd.DataFrame({"Month": summary["Month"], "Net worth": summary["Closing"],
                             f"{gname} (counted accounts)": summary[gacc].sum(axis=1) if gacc else 0.0})
        fig = px.line(hist.melt("Month", var_name="Series", value_name="Amount"), x="Month", y="Amount",
                      color="Series", markers=True)
        fig.add_hline(y=float(gsel["target"]), line_dash="dash", annotation_text="Target")
        fig.update_xaxes(type="category")
        show_chart(fig, 340)

    st.subheader("Add or edit a goal")
    st.caption("Progress counts the balance of the accounts you tick. To make real progress, move money there with "
               "a Transfer (for example Cash to Money Market). Shares count at cost, not market value.")
    pick = st.selectbox("Goal", ["New goal"] + goals["name"].tolist(), key="goal_pick")
    cg = goals[goals["name"] == pick].iloc[0] if pick != "New goal" else None
    has_dl0 = cg is not None and pd.notna(cg["deadline"]) and bool(cg["deadline"])
    dl0 = pd.to_datetime(cg["deadline"]).date() if has_dl0 else date(today.year + 1, today.month, 1)
    acc0 = ([x for x in str(cg["accounts"]).split(",") if x in acc_names] if cg is not None
            else [x for x in ("Money Market", "Bank", "Equity (Stocks)") if x in acc_names])
    form_n = st.session_state.get("goal_form_n", 0)      # bumped after a save so the form resets
    with st.form(f"goal_form_{pick}_{form_n}"):
        g_name = st.text_input("Name", value=cg["name"] if cg is not None else "")
        g_target = st.number_input("Target amount", min_value=0.0, step=1000.0, format="%.2f",
                                   value=float(cg["target"]) if cg is not None else 0.0)
        g_has_dl = st.checkbox("This goal has a deadline", value=has_dl0)
        g_dl = st.date_input("Deadline", value=dl0)
        g_accs = st.multiselect("Accounts that count toward it", pick_accounts, default=acc0)
        if st.form_submit_button("Save goal"):
            clash = goals[(goals["name"] == g_name.strip()) & (goals["id"] != (cg["id"] if cg is not None else -1))]
            if not g_name.strip():
                st.error("Give the goal a name.")
            elif g_target <= 0:
                st.error("The target must be greater than zero.")
            elif not g_accs:
                st.error("Pick at least one account to count.")
            elif not clash.empty:
                st.error("You already have a goal with that name.")
            else:
                vals = (g_name.strip(), g_target, str(g_dl) if g_has_dl else None, ",".join(g_accs))
                if cg is None:
                    run("INSERT INTO goals (name, target, deadline, accounts) VALUES (?, ?, ?, ?)", vals)
                else:
                    run("UPDATE goals SET name = ?, target = ?, deadline = ?, accounts = ? WHERE id = ?",
                        vals + (int(cg["id"]),))
                st.session_state["goal_form_n"] = form_n + 1
                flash("Goal saved.", "🎯")
                st.rerun()
    if cg is not None:
        sure_goal = st.checkbox("Yes, delete this goal (your transactions are not affected)", key="goal_del_ok")
        if st.button("Delete goal", disabled=not sure_goal):
            run("DELETE FROM goals WHERE id = ?", (int(cg["id"]),))
            flash("Goal deleted.", "🗑️")
            st.rerun()

    st.subheader("What-if planner")
    if goals.empty:
        st.info("Add a goal above to try what-ifs on it.")
    else:
        wg = st.selectbox("Goal", goals["name"].tolist(), key="wi_goal")
        wrow = goals[goals["name"] == wg].iloc[0]
        wacc = [x for x in str(wrow["accounts"]).split(",") if x in acc_names]
        w_start = float(bal_now[wacc].sum()) if wacc else 0.0
        w_target = float(wrow["target"])
        st.caption(f"Starting from {fmt(w_start)} saved toward {fmt(w_target)}. Returns are your assumption, not a promise; "
                   "they ignore fees and tax.")
        w1, w2 = st.columns(2)
        w_pmt = w1.number_input("Save per month", min_value=0.0, value=float(round(max(pace, 0.0))), step=500.0,
                                key=f"wi_pmt_{wg}")
        w_ret = w2.slider("Assumed return per year (%)", 0.0, 25.0, 8.0, 0.5, key="wi_ret") / 100
        w3, w4 = st.columns(2)
        w_raise = w3.slider("Raise your monthly saving each year by (%)", 0, 30, 0, key="wi_raise") / 100
        w_infl = w4.slider("Inflation per year (%), optional", 0.0, 20.0, 0.0, 0.5, key="wi_infl") / 100

        base_m = ledger.months_to_reach(w_start, w_target, max(pace, 0.0), 0.0, 0.0)
        scen_m = ledger.months_to_reach(w_start, w_target, w_pmt, w_ret, w_raise)

        def when(m):
            return "not within 100 years" if m is None else (f"{m // 12} yr {m % 12} mo (around "
                                                             f"{pd.Period(date.today(), 'M') + m})" if m else "reached")
        m1, m2 = st.columns(2)
        m1.metric("At your recent pace, no returns", when(base_m))
        m2.metric("This scenario", when(scen_m),
                  delta=(f"{(base_m - scen_m) // 12} yr {(base_m - scen_m) % 12} mo sooner"
                         if base_m is not None and scen_m is not None and scen_m < base_m else None))
        if scen_m and w_infl > 0:
            st.caption(f"With {w_infl:.1%} inflation, {fmt(w_target)} when you get there buys what about "
                       f"{fmt(w_target / (1 + w_infl) ** (scen_m / 12))} buys today.")

        pa, pb = st.columns(2)
        want = pa.date_input("I want to be there by", value=(pd.to_datetime(wrow["deadline"]).date()
                             if pd.notna(wrow["deadline"]) and wrow["deadline"] else date.today() + timedelta(days=3 * 365)),
                             key=f"wi_date_{wg}")
        n_m = max((want.year - date.today().year) * 12 + want.month - date.today().month, 1)
        need = ledger.needed_saving(w_start, w_target, n_m, w_ret, w_raise)
        pb.metric(f"Needed per month to reach it by {want}", fmt(need),
                  delta=f"{signed(need - pace)} versus your recent pace",
                  delta_color="inverse")

        horizon = min((scen_m if scen_m is not None else 480) + 12, 480)
        hist_a = ledger.project(w_start, w_pmt, w_ret, w_raise, None, horizon)
        hist_b = ledger.project(w_start, max(pace, 0.0), 0.0, 0.0, None, horizon)
        idx = [(pd.Period(date.today(), "M") + k).to_timestamp() for k in range(horizon + 1)]
        plot = pd.DataFrame({"Month": idx, "This scenario": hist_a, "Recent pace, no returns": hist_b}).melt(
            "Month", var_name="Line", value_name="Saved")
        fig = px.line(plot, x="Month", y="Saved", color="Line")
        fig.add_hline(y=w_target, line_dash="dash", annotation_text="Target")
        show_chart(fig, 340)

        st.caption("What each extra amount a month would change (same return and raise as above):")
        rows_w = []
        for extra in (1000, 2000, 5000):
            m_x = ledger.months_to_reach(w_start, w_target, w_pmt + extra, w_ret, w_raise)
            rows_w.append({"Extra per month": extra, "Gets you there in": when(m_x),
                           "Sooner by": (f"{(scen_m - m_x) // 12} yr {(scen_m - m_x) % 12} mo"
                                         if scen_m is not None and m_x is not None else "")})
        st.dataframe(pd.DataFrame(rows_w), hide_index=True, **WIDE)


with tab_rec:
    st.caption("A rule adds its entry on the chosen day of every month. Entries are created the next time the app "
               "opens, so months you missed are filled in. This only records in the ledger; it never moves real money.")
    if rules.empty:
        st.info("No recurring entries yet. Good first ones: your allowance, a fixed bill, or a transfer to Money "
                "Market right after payday.")
    else:
        def next_of(r):
            n = ledger.next_due(int(r.day), date.fromisoformat(r.start_date),
                                date.fromisoformat(r.last_date) if pd.notna(r.last_date) and r.last_date else None,
                                date.today())
            return n.isoformat() if n else ""
        shown = pd.DataFrame({
            "Name": rules["name"], "Type": rules["type"], "Amount": rules["amount"],
            "Category": rules["category"].fillna(""),
            "Account": [f"{r.account} → {r.to_account}" if r.type == "Transfer" else r.account
                        for r in rules.itertuples()],
            "Day": rules["day"], "Next entry": [next_of(r) for r in rules.itertuples()],
            "Last entry": rules["last_date"].fillna(""), "Active": rules["active"].astype(bool)})
        st.dataframe(shown, hide_index=True,
                     column_config={"Amount": st.column_config.NumberColumn(format="%.2f")}, **WIDE)

    st.subheader("Add or edit a rule")
    rpos = lambda opts, v: opts.index(v) if v in opts else 0                       # noqa: E731
    rpick = st.selectbox("Rule", ["New rule"] + rules["name"].tolist(), key="rec_pick")
    cr = rules[rules["name"] == rpick].iloc[0] if rpick != "New rule" else None
    rn = st.session_state.get("rec_form_n", 0)                  # bumped after a save so the form resets
    r_type = st.radio("Type", TYPES, horizontal=True, index=TYPES.index(cr["type"]) if cr is not None else 1,
                      key=f"rec_type_{rpick}_{rn}")
    with st.form(f"rec_form_{rpick}_{rn}"):
        r_name = st.text_input("Name", value=cr["name"] if cr is not None else "",
                               placeholder="e.g. Monthly allowance, Internet bill, Payday saving")
        r_amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f",
                                   value=float(cr["amount"]) if cr is not None else 0.0)
        same = cr is not None and cr["type"] == r_type
        if r_type == "Transfer":
            r_from = st.selectbox("From account", pick_accounts,
                                  index=rpos(pick_accounts, cr["account"]) if same else 0)
            r_to = st.selectbox("To account", pick_accounts,
                                index=rpos(pick_accounts, cr["to_account"]) if same else min(1, len(pick_accounts) - 1))
            r_cat = None
        else:
            opts = entry_cats(r_type, keep=cr["category"] if cr is not None and same else None)
            r_cat = st.selectbox("Category", opts, index=rpos(opts, cr["category"]) if same else 0)
            r_from = st.selectbox("Account", pick_accounts,
                                  index=rpos(pick_accounts, cr["account"]) if cr is not None else 0)
            r_to = None
        r_day = st.number_input("Day of the month", min_value=1, max_value=31, step=1,
                                value=int(cr["day"]) if cr is not None else 1,
                                help="31 means the last day, so it still works in shorter months.")
        if cr is None:
            r_start = st.date_input("Starts on", value=date.today(), min_value=date.today() - timedelta(days=365),
                                    help="Any due dates between this day and today are added straight away.")
        r_active = st.checkbox("Active", value=bool(cr["active"]) if cr is not None else True)
        if st.form_submit_button("Save rule"):
            clash = rules[(rules["name"] == r_name.strip()) & (rules["id"] != (cr["id"] if cr is not None else -1))]
            if not r_name.strip():
                st.error("Give the rule a name.")
            elif r_amount <= 0:
                st.error("Amount must be greater than zero.")
            elif r_type != "Transfer" and r_cat is None:
                st.error("Add a category for this type first.")
            elif r_type == "Transfer" and r_from == r_to:
                st.error("Pick two different accounts.")
            elif not clash.empty:
                st.error("You already have a rule with that name.")
            else:
                vals = (r_name.strip(), r_type, r_amount, cat_id.get(r_cat), acc_id[r_from], acc_id.get(r_to),
                        int(r_day))
                if cr is None:
                    run("INSERT INTO recurring (name, type, amount, category_id, account_id, to_account_id, day, "
                        "start_date, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", vals + (str(r_start), int(r_active)))
                else:
                    run("UPDATE recurring SET name=?, type=?, amount=?, category_id=?, account_id=?, "
                        "to_account_id=?, day=?, active=? WHERE id=?", vals + (int(r_active), int(cr["id"])))
                st.session_state["rec_form_n"] = rn + 1
                flash("Rule saved.", "🔁")
                st.rerun()
    if cr is not None:
        rec_ok = st.checkbox("Yes, delete this rule (entries it already created stay)", key="rec_del_ok")
        if st.button("Delete rule", disabled=not rec_ok):
            run("DELETE FROM recurring WHERE id = ?", (int(cr["id"]),))
            flash("Rule deleted.", "🗑️")
            st.rerun()

with tab_loan:
    t_day = date.today()

    st.caption("Lending or borrowing is not spending or income. Money you lend moves to 'Loans receivable' (still yours) "
               "and money you borrow shows as 'Loans payable' (subtracted from net worth), so your budgets stay honest.")
    k1, k2, k3 = st.columns(3)
    k1.metric("Owed to you", fmt(owed_to_me))
    k2.metric("You owe", fmt(i_owe))
    k3.metric("Net", fmt(owed_to_me - i_owe))
    if overdue_rows:
        st.error("Overdue: " + ", ".join(f"{r['Person']} ({fmt(r['Outstanding'])}, due {r['Due']})" for r in overdue_rows))
    if loan_rows:
        st.dataframe(pd.DataFrame(loan_rows).drop(columns="id"), hide_index=True, **WIDE)
    else:
        st.info("No loans yet. Record money you lent to a friend or borrowed from family below.")

    st.subheader("New loan or IOU")
    ldir = st.radio("This is money...", ["I lent", "I borrowed"], horizontal=True, key="loan_dir")
    lform_n = st.session_state.get("loan_form_n", 0)
    with st.form(f"loan_form_{lform_n}"):
        l_person = st.text_input("Person")
        l_amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f")
        l_acc = st.selectbox("Account the money left" if ldir == "I lent" else "Account the money went into",
                             pick_accounts, format_func=label)
        l_date = st.date_input("Date", value=date.today())
        l_has_due = st.checkbox("It has a due date")
        l_due = st.date_input("Due date", value=date.today() + timedelta(days=30))
        l_note = st.text_input("Note (optional)")
        if st.form_submit_button("Save loan"):
            if not l_person.strip():
                st.error("Enter the person's name.")
            elif l_amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                who = l_person.strip()
                with ledger.connect() as conn:
                    new_id = conn.execute("INSERT INTO loans (person, direction, due_date, note) VALUES (?, ?, ?, ?)",
                                          (who, "lent" if ldir == "I lent" else "borrowed",
                                           str(l_due) if l_has_due else None, l_note.strip())).lastrowid
                    src_a, dst_a, why = ((acc_id[l_acc], acc_id[RECV], f"Lent to {who}") if ldir == "I lent"
                                         else (acc_id[PAY], acc_id[l_acc], f"Borrowed from {who}"))
                    conn.execute("INSERT INTO transactions (date, amount, type, account_id, to_account_id, description, "
                                 "loan_id) VALUES (?, ?, 'Transfer', ?, ?, ?, ?)",
                                 (str(l_date), l_amount, src_a, dst_a, why, new_id))
                st.session_state["loan_form_n"] = lform_n + 1
                if ldir == "I lent" and bal_now[l_acc] - l_amount < 0:
                    flash(f"Loan saved - but {l_acc} is now below zero.", "⚠️")
                else:
                    flash("Loan saved.", "🤝")
                st.rerun()

    st.subheader("Record a repayment or write-off")
    open_loans = [r for r in loan_rows if r["Outstanding"] >= 0.005]
    if not open_loans:
        st.info("Nothing outstanding.")
    else:
        names_l = {r["id"]: f"{r['Person']} - {r['Type'].lower()} - {fmt(r['Outstanding'])} outstanding" for r in open_loans}
        lid_sel = st.selectbox("Loan", list(names_l), format_func=names_l.get, key="loan_pick")
        cur_l = next(r for r in open_loans if r["id"] == lid_sel)
        lent_l = cur_l["Type"] == "You lent"
        with st.form(f"repay_form_{lid_sel}_{lform_n}"):
            rp_amount = st.number_input("Amount", min_value=0.0, step=100.0, format="%.2f",
                                        value=float(cur_l["Outstanding"]))
            rp_acc = st.selectbox("Account the money went into" if lent_l else "Account you paid from",
                                  pick_accounts, format_func=label)
            rp_date = st.date_input("Date", value=date.today())
            if st.form_submit_button("Record repayment"):
                if rp_amount <= 0 or rp_amount > cur_l["Outstanding"] + 0.005:
                    st.error(f"Enter an amount between 0 and {fmt(cur_l['Outstanding'])}.")
                else:
                    src_a, dst_a, why = ((acc_id[RECV], acc_id[rp_acc], f"Repaid by {cur_l['Person']}") if lent_l
                                         else (acc_id[rp_acc], acc_id[PAY], f"Repaid to {cur_l['Person']}"))
                    run("INSERT INTO transactions (date, amount, type, account_id, to_account_id, description, loan_id) "
                        "VALUES (?, ?, 'Transfer', ?, ?, ?, ?)", (str(rp_date), rp_amount, src_a, dst_a, why, int(lid_sel)))
                    st.session_state["loan_form_n"] = lform_n + 1
                    if not lent_l and bal_now[rp_acc] - rp_amount < 0:
                        flash(f"Repayment saved - but {rp_acc} is now below zero.", "⚠️")
                    else:
                        flash("Repayment recorded.", "💵")
                    st.rerun()
        if lent_l:
            wo_ok = st.checkbox("Write off what's left as a loss (it will count as spending)", key=f"wo_ok_{lid_sel}")
            if st.button("Write off remaining", disabled=not wo_ok, key=f"wo_btn_{lid_sel}"):
                run("INSERT INTO transactions (date, amount, type, category_id, account_id, description, loan_id) "
                    "VALUES (?, ?, 'Outflow', ?, ?, ?, ?)",
                    (str(date.today()), float(cur_l["Outstanding"]), cat_id["Loan written off"], acc_id[RECV],
                     f"Written off: {cur_l['Person']}", int(lid_sel)))
                flash("Written off.", "🧾")
                st.rerun()

    if loan_rows:
        st.subheader("Delete a loan")
        all_names = {r["id"]: f"{r['Person']} - {r['Type'].lower()} - {fmt(r['Original'])}" for r in loan_rows}
        dl_id = st.selectbox("Loan", list(all_names), format_func=all_names.get, key="loan_del_pick")
        dl_ok = st.checkbox("Yes, delete this loan and all its entries (a backup is made first)", key="loan_del_ok")
        if st.button("Delete loan", disabled=not dl_ok):
            ledger.backup("pre_delete")
            run("DELETE FROM transactions WHERE loan_id = ?", (int(dl_id),))
            run("DELETE FROM loans WHERE id = ?", (int(dl_id),))
            flash("Loan deleted.", "🗑️")
            st.rerun()

with tab_review:
    sp = pd.Period(sel)
    prev_row = summary[summary["Month"] == str(sp - 1)]
    inc, spend = srow["Inflows"], srow["Outflows"]
    net_m = inc - spend
    rate_m = net_m / inc if inc else None
    plan = save_min
    md, acts = [], []
    P = md.append

    P(f"## Monthly review: {sel}")
    if sp == cur_month:
        P(f"*This month is still in progress (up to {date.today():%d %b}).*")
    P("### The numbers")
    P(f"- **Money in:** {fmt(inc)}")
    P(f"- **Money out:** {fmt(spend)}")
    P(f"- **Saved:** {fmt(net_m)}" + (f" ({rate_m:.0%} of income; your plan is {plan:.0f}%, stretch {save_stretch:.0f}%)" if rate_m is not None else ""))
    if not prev_row.empty:
        pv = prev_row.iloc[0]
        P(f"- **Versus {sp - 1}:** income {signed(inc - pv['Inflows'])}, spending {signed(spend - pv['Outflows'])}, "
          f"saved {signed(net_m - (pv['Inflows'] - pv['Outflows']))}")

    P("### Your spending pools")

    def pool_line(name, sp_, lim_):
        if lim_ <= 0:
            return f"- **{name}:** spent {fmt(sp_)} (no pool, because no income was recorded)"
        tag = f"**over by {fmt(sp_ - lim_)}**" if sp_ > lim_ + 0.005 else f"{fmt(lim_ - sp_)} left"
        return f"- **{name}:** {fmt(sp_)} of {fmt(lim_)} ({sp_ / lim_:.0%}), {tag}"
    P(pool_line(f"Leisure pool ({leisure_pct:.0f}%)", leis_spent, leis_limit))
    P(pool_line(f"Everything else ({needs_pct:.0f}%)", needs_spent, needs_limit))

    mo = tx[(tx["month"] == sp) & (tx["type"] == "Outflow")]
    by_cat = mo.groupby("category")["amount"].sum().sort_values(ascending=False)
    P("### Where the money went")
    if by_cat.empty:
        P("- No spending recorded.")
    for c_, v_ in by_cat.head(5).items():
        P(f"- {c_}: {fmt(v_)} ({v_ / spend:.0%})")
    for r in mo.sort_values("amount", ascending=False).head(3).itertuples():
        P(f"- Big one: {r.date:%d %b}, {r.category}, {fmt(r.amount)}" + (f" ({r.description})" if r.description else ""))
    if not prev_row.empty:
        pc = tx[(tx["month"] == sp - 1) & (tx["type"] == "Outflow")].groupby("category")["amount"].sum()
        chg = by_cat.sub(pc, fill_value=0).sort_values()
        ups, downs = chg[chg > 0].tail(3)[::-1], chg[chg < 0].head(3)
        if len(ups) or len(downs):
            P(f"### Biggest changes versus {sp - 1}")
            for c_, v_ in ups.items():
                P(f"- Up: {c_} {signed(v_)}")
            for c_, v_ in downs.items():
                P(f"- Down: {c_} {signed(v_)}")

    P("### Savings goals")
    if goals.empty:
        P("- No goals set yet.")
    for g_ in goals.itertuples():
        accs_ = [x for x in str(g_.accounts).split(",") if x in acc_names]
        end_v = float(balances(sp.end_time)[accs_].sum()) if accs_ else 0.0
        start_v = float(balances(sp.start_time - pd.Timedelta(days=1))[accs_].sum()) if accs_ else 0.0
        line = f"- **{g_.name}:** {fmt(end_v)} of {fmt(g_.target)} ({end_v / g_.target:.0%}), {signed(end_v - start_v)} this month"
        if pd.notna(g_.deadline) and g_.deadline and end_v < g_.target:
            dl_ = pd.to_datetime(g_.deadline).date()
            if dl_ > date.today():
                need_ = (g_.target - end_v) / max((dl_ - date.today()).days / 30.44, 1.0)
                line += f"; needs about {fmt(need_)} a month to hit {dl_}"
                if need_ > pace:
                    acts.append(f"Goal '{g_.name}' needs about {fmt(need_)} a month but your recent pace is {fmt(pace)}.")
        P(line)

    P("### Loans")
    if not loan_rows:
        P("- No loans recorded.")
    else:
        P(f"- Owed to you: {fmt(owed_to_me)}. You owe: {fmt(i_owe)}.")
        for r in overdue_rows:
            P(f"- **Overdue:** {r['Person']} {fmt(r['Outstanding'])} (due {r['Due']})")
            acts.append(f"Follow up on {r['Person']}'s {fmt(r['Outstanding'])}, which was due {r['Due']}.")

    P("### Balance checks")
    found = mo[mo["category"] == "Balance adjustment (shortfall)"]["amount"].sum()
    if checks.empty:
        P("- You haven't compared the ledger with your real balances yet.")
        acts.append("Do a balance check on Cash in the Manage tab.")
    else:
        last_c = checks[checks["account"] == "Cash"]
        P("- Last check: " + ", ".join(f"{a_} on {d_}" for a_, d_ in
                                       checks.groupby("account")["date"].max().items()))
        if last_c.empty or (date.today() - pd.to_datetime(last_c["date"].max()).date()).days > 30:
            acts.append("It's been over 30 days since your last Cash balance check. Count the real money.")
    if found > 0:
        P(f"- Checks found {fmt(found)} of spending you hadn't logged this month.")

    if rate_m is not None and rate_m * 100 < plan - 1:
        acts.insert(0, f"You saved {rate_m:.0%} against a plan of {plan:.0f}%. At this income, reaching the plan means "
                       f"saving {fmt(inc * plan / 100 - net_m)} more.")
    if leis_spent > leis_limit + 0.005 and leis_limit > 0:
        acts.append(f"Leisure went {fmt(leis_spent - leis_limit)} over its pool. Next month, hold gaming, snacks and the "
                    f"other leisure categories to {fmt(leis_limit)} together, or raise the pool on purpose.")
    if needs_spent > needs_limit + 0.005 and needs_limit > 0:
        acts.append(f"Everything else went {fmt(needs_spent - needs_limit)} over its pool. Look at the biggest items "
                    "above before changing the plan.")
    P("### What to do next")
    for t_ in (acts or ["Nothing flagged. Keep logging as you spend, and move your saving to a goal account when income arrives."])[:6]:
        P(f"- {t_}")

    review_md = "\n".join(md)
    st.markdown(review_md)
    st.download_button("⬇️ Download this review", review_md, f"review_{sel}.md", "text/markdown")

with tab_manage:
    st.caption("To change a transaction's *type*, delete it and record it again.")
    pick = tx.sort_values(["date", "id"], ascending=False)
    names = {int(r.id): f"{r.date:%Y-%m-%d} · {r.type} · {fmt(r.amount)} · "
                        f"{r.category if pd.notna(r.category) else r.account}"
                        + (f" · {str(r.description)[:28]}" if isinstance(r.description, str) and r.description else "")
                        for r in pick.itertuples()}
    if not names:
        st.info("No transactions yet.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("### Edit")
            eid = st.selectbox("Transaction", list(names), format_func=names.get, key="edit_pick")
            r = tx[tx["id"] == eid].iloc[0]
            with st.form(f"edit_{eid}"):
                e_date = st.date_input("Date", value=r["date"].date(), key=f"d{eid}")
                e_amt = st.number_input("Amount", value=float(r["amount"]), min_value=0.0, step=100.0,
                                        format="%.2f", key=f"a{eid}")
                pos = lambda opts, v: opts.index(v) if v in opts else 0           # noqa: E731
                if r["type"] == "Transfer":
                    e_from = st.selectbox("From", acc_names, index=pos(acc_names, r["account"]), key=f"f{eid}")
                    e_to = st.selectbox("To", acc_names, index=pos(acc_names, r["to_account"]), key=f"t{eid}")
                    e_cat = None
                else:
                    opts = entry_cats(r["type"], keep=r["category"])
                    e_cat = st.selectbox("Category", opts, index=pos(opts, r["category"]), key=f"c{eid}")
                    e_from, e_to = st.selectbox("Account", acc_names, index=pos(acc_names, r["account"]),
                                                key=f"f{eid}"), None
                e_desc = st.text_input("Notes", value=str(r["description"] or ""), key=f"n{eid}")
                if st.form_submit_button("Update transaction"):
                    if e_amt <= 0:
                        st.error("Amount must be greater than zero.")
                    elif r["type"] == "Transfer" and e_from == e_to:
                        st.error("Pick two different accounts.")
                    else:
                        run("UPDATE transactions SET date=?, amount=?, category_id=?, account_id=?, "
                            "to_account_id=?, description=? WHERE id=?",
                            (str(e_date), e_amt, cat_id.get(e_cat), acc_id[e_from], acc_id.get(e_to), e_desc, int(eid)))
                        flash(f"Transaction #{eid} updated.")
                        st.rerun()
        with right:
            st.markdown("### Delete")
            did = st.selectbox("Transaction", list(names), format_func=names.get, key="del_pick")
            sure = st.checkbox("Yes, delete it (a backup is made first)")
            if st.button("Delete transaction", disabled=not sure):
                ledger.backup("pre_delete")
                run("DELETE FROM transactions WHERE id = ?", (int(did),))
                flash(f"Transaction #{did} deleted.", "🗑️")
                st.rerun()

    st.divider()
    st.markdown("### Smart categories")
    st.caption("When you type what you bought (in Quick add), the app suggests a category: first from the keyword rules "
               "below, then from what you usually pick for the same words. Add your own words to teach it.")
    with st.expander(f"Keyword rules ({len(kw_rows)})"):
        st.dataframe(kw_rows[["keyword", "category", "type"]].rename(columns=str.title), hide_index=True, **WIDE)
    with st.form("kw_form", clear_on_submit=True):
        k1, k2 = st.columns(2)
        k_word = k1.text_input("Word or phrase", placeholder="e.g. daraz")
        k_cat = k2.selectbox("Category", entry_cats("Outflow") + entry_cats("Inflow"))
        if st.form_submit_button("Add keyword"):
            if not k_word.strip():
                st.error("Enter a word or phrase.")
            else:
                run("INSERT OR IGNORE INTO keywords (keyword, category_id) VALUES (?, ?)",
                    (" ".join(k_word.lower().split()), cat_id[k_cat]))
                flash("Keyword added.", "🧠")
                st.rerun()
    if len(kw_rows):
        kd1, kd2 = st.columns([3, 1])
        kw_pick = kd1.selectbox("Remove a keyword", kw_rows["id"].tolist(), key="kw_del_pick", format_func=lambda i: (
            f"{kw_rows.loc[kw_rows['id'] == i, 'keyword'].iloc[0]} → {kw_rows.loc[kw_rows['id'] == i, 'category'].iloc[0]}"))
        if kd2.button("Remove"):
            run("DELETE FROM keywords WHERE id = ?", (int(kw_pick),))
            flash("Keyword removed.", "🧠")
            st.rerun()

    st.markdown("#### Tidy up uncategorised entries")
    loose = tx[tx["type"].isin(["Inflow", "Outflow"]) & tx["category"].isin(["Other", "Uncategorised"])]
    fixes = []
    for r_ in loose.itertuples():
        found, why = suggest(r_.description if isinstance(r_.description, str) else "", r_.type)
        if found and found != r_.category:
            fixes.append((int(r_.id), r_.date.date(), r_.description, r_.category, found, why))
    if fixes:
        st.dataframe(pd.DataFrame(fixes, columns=["id", "Date", "Note", "Now", "Suggested", "Because"]).drop(columns="id"),
                     hide_index=True, **WIDE)
        fix_ok = st.checkbox(f"Yes, apply these {len(fixes)} suggestion(s)", key="fix_ok")
        if st.button("Apply suggestions", disabled=not fix_ok):
            for tid, _, _, _, new_cat, _ in fixes:
                run("UPDATE transactions SET category_id = ? WHERE id = ?", (cat_id[new_cat], tid))
            flash(f"{len(fixes)} entries re-categorised.", "🧠")
            st.rerun()
    else:
        st.caption("Nothing to suggest right now. Entries in 'Other' or 'Uncategorised' with a recognisable note would "
                   "show up here.")

    st.divider()
    st.markdown("### Balance check")
    st.caption("Count the real money (cash in hand, wallet or bank app) and enter it. The ledger shows any gap and "
               "can record it, so small forgotten entries don't pile up.")
    n_future = int((tx["date"] > pd.Timestamp(date.today())).sum())
    if n_future:
        st.info(f"{n_future} entr{'y is' if n_future == 1 else 'ies are'} dated after today and not counted here, "
                "because the money hasn't moved yet.")
    chk_acc = st.selectbox("Account to check", pick_accounts, key="chk_acc")
    expected = round(float(balances(pd.Timestamp(date.today()))[chk_acc]), 2)
    actual = st.number_input("Real balance right now", value=expected, step=100.0, format="%.2f",
                             key=f"chk_actual_{chk_acc}_{expected}")
    gap = round(actual - expected, 2)
    b1, b2 = st.columns(2)
    b1.metric("Ledger says", fmt(expected))
    b2.metric("Difference (real minus ledger)", fmt(gap))

    def log_check(adjusted):
        run("INSERT INTO balance_checks (date, account_id, expected, actual, adjusted) VALUES (?, ?, ?, ?, ?)",
            (str(date.today()), acc_id[chk_acc], expected, actual, int(adjusted)))

    if abs(gap) < 0.005:
        st.success("Matches. Your ledger and the real money agree.")
        if st.button("Log this check"):
            log_check(False)
            flash("Check logged.", "⚖️")
            st.rerun()
    else:
        st.warning(("You have MORE real money than the ledger shows, so some income wasn't recorded."
                    if gap > 0 else "You have LESS real money than the ledger shows, so some spending wasn't recorded.")
                   + " The best fix is to find and add the missing entries; if you can't, record the gap.")
        c_a, c_b = st.columns(2)
        if c_a.button(f"Record the gap ({fmt(abs(gap))}) as an adjustment"):
            kind, cname = (("Inflow", "Balance adjustment (surplus)") if gap > 0
                           else ("Outflow", "Balance adjustment (shortfall)"))
            run("INSERT INTO transactions (date, amount, type, category_id, account_id, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(date.today()), abs(gap), kind, cat_id[cname], acc_id[chk_acc],
                 f"Balance check: ledger {expected:,.2f}, counted {actual:,.2f}"))
            log_check(True)
            flash("Adjustment recorded.", "⚖️")
            st.rerun()
        if c_b.button("Log the check without adjusting"):
            log_check(False)
            flash("Check logged (no adjustment).", "⚖️")
            st.rerun()
    if not checks.empty:
        st.caption("Recent checks")
        st.dataframe(checks.head(8).assign(adjusted=lambda d: d["adjusted"].astype(bool))
                     .rename(columns={"date": "Date", "account": "Account", "expected": "Ledger", "actual": "Counted",
                                      "adjusted": "Adjusted"}), hide_index=True, **WIDE)


with tab_data:
    d1, d2, d3 = st.columns(3)
    export = tx.drop(columns=["month", "category_id", "account_id", "to_account_id"])
    d1.download_button("⬇️ Transactions (CSV)", export.to_csv(index=False), "transactions.csv", "text/csv")
    d2.download_button("⬇️ Full database", ledger.DB_PATH.read_bytes(), "ledger.db")
    if d3.button("💾 Back up now"):
        flash(f"Backup saved: {ledger.backup('manual').name}")
        st.rerun()
    n_bk = len(list(ledger.BACKUP_DIR.glob("ledger_*.db"))) if ledger.BACKUP_DIR.exists() else 0
    st.caption(f"{n_bk} backup(s) in {ledger.BACKUP_DIR}. Opening balances (before your first transaction):")
    st.dataframe(accounts.rename(columns={"name": "Account", "opening_balance": "Opening balance"})
                 [["Account", "Opening balance"]], hide_index=True)

    st.subheader("Excel workbook")
    st.caption("A formatted workbook with Summary, Transactions, By category, Budget and Goals and loans sheets. Totals are live "
               "formulas, so you can edit or add rows in Excel and everything recalculates. It holds your finances, so keep "
               "the file private.")
    if st.button("Create Excel file", key="xl_make"):
        try:
            goals_x = goals.copy()
            goals_x["saved_now"] = [float(bal_now[[x for x in str(acc_s).split(",") if x in acc_names]].sum())
                                    for acc_s in goals_x["accounts"]]
            st.session_state["xlsx_bytes"] = exporter.build_workbook(
                tx, accounts, summary, cats, goals_x, loan_rows, {"save_min": save_min, "leisure_pct": leisure_pct},
                CURRENCY, account_cols=VISIBLE)
            st.session_state["xlsx_name"] = f"Smart Ledger {date.today():%Y-%m-%d}.xlsx"
        except RuntimeError as err:
            st.error(str(err))
        except Exception as err:                                  # show a readable message instead of a traceback
            st.error(f"Couldn't build the Excel file ({type(err).__name__}: {err}). Please send me this message.")
    if st.session_state.get("xlsx_bytes"):
        st.download_button("Download the Excel file", st.session_state["xlsx_bytes"],
                           file_name=st.session_state.get("xlsx_name", "Smart Ledger.xlsx"),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="xl_dl")

    st.subheader("Automatic backups")
    st.caption("The first time you open the app each day, it saves a backup on this PC and, if you set an off-PC "
               "folder such as Dropbox, copies it there too. This happens when the app is opened, not in the background. "
               "Backup files are not encrypted, so protect the Dropbox account with a strong password and two-step login.")
    st.write(f"Last automatic backup: {ledger.get_setting('last_backup_status') or 'none yet'}")
    bd = st.text_input("Off-PC backup folder", value=ledger.get_setting("backup_dir") or ledger.detect_dropbox(),
                       key="backup_dir_input", help="For example C:\\Users\\you\\Dropbox\\Smart ledger backups. "
                       "The last part is created for you if the Dropbox folder exists. Leave empty to turn off.")
    if st.button("Save folder and test it"):
        folder = bd.strip()
        if not folder:
            ledger.set_setting("backup_dir", "")
            flash("Off-PC copies turned off.", "☁️")
            st.rerun()
        try:
            ledger.copy_offsite(ledger.backup("test"), folder, f"ledger_{date.today()}.db")
            ledger.set_setting("backup_dir", folder)
            ledger.set_setting("last_backup_status", f"{date.today()}: copied to {folder}")
            flash("Folder saved and a backup was copied there.", "☁️")
            st.rerun()
        except OSError as e:
            st.error(f"Couldn't copy to that folder: {e}")

    st.subheader("Restore from a backup")
    st.caption("Replaces ALL current data with the chosen backup. A safety copy of today's data is made first, and your "
               "PIN and backup folder are kept.")
    files = ledger.list_backups()
    if files:
        pick_bk = st.selectbox("Backup file", files, format_func=lambda p: f"{p.name}   ({p.parent.name})",
                               key="restore_pick")
        sure_r = st.checkbox("Yes, replace my current data with this backup", key="restore_ok")
        if st.button("Restore this backup", disabled=not sure_r):
            try:
                safety = ledger.restore_backup(pick_bk)
                flash(f"Restored. Your previous data is saved as {safety.name}.", "♻️")
                st.rerun()
            except (ValueError, OSError) as e:
                st.error(str(e))
    else:
        st.info("No backup files found yet.")

    st.subheader("Open it on your phone")
    try:
        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _s.connect(("10.255.255.255", 1))
        lan_ip = _s.getsockname()[0]
        _s.close()
    except OSError:
        lan_ip = None
    port = st.get_option("server.port") or 8501
    if lan_ip:
        st.code(f"http://{lan_ip}:{port}", language=None)
        st.caption("Quick-add page for your phone (add this one to your home screen):")
        st.code(f"http://{lan_ip}:{port}/?mode=quick", language=None)
    else:
        st.warning("Couldn't work out this PC's Wi-Fi address. Connect to Wi-Fi and refresh.")
    st.markdown(
        "- Your phone and this PC must be on the **same home Wi-Fi**, and the black launcher window must be open.\n"
        "- The first time, Windows may ask to allow access. Tick **Private networks** only.\n"
        "- On a phone the **Record transaction** panel is behind the small arrow at the top left.\n"
        "- The link isn't encrypted, so use it only on Wi-Fi you trust, never on public Wi-Fi, and never forward "
        "this port on your router.\n"
        "- The address can change if your router hands out a new one; this page always shows the current one.")

    st.subheader("Change PIN")
    with st.form("pin_change", clear_on_submit=True):
        old_pin = st.text_input("Current PIN", type="password")
        new1 = st.text_input("New PIN / password", type="password")
        new2 = st.text_input("Repeat the new one", type="password")
        if st.form_submit_button("Change PIN"):
            ok, msg = ledger.check_pin(old_pin)
            if not ok:
                st.error(msg)
            elif len(new1) < 6:
                st.error("Use at least 6 characters.")
            elif new1 != new2:
                st.error("The two new entries don't match.")
            else:
                ledger.set_pin(new1)
                flash("PIN changed.", "🔑")
                st.rerun()
