"""Look and feel for Smart Ledger.

Direction: a private-bank statement, modernised. Bottle-green paper, ivory ink, brass for the one thing to act on.
Numbers are set in a serif with tabular figures and sit in ruled rows like a ledger; a double rule under a figure
marks a closing balance, as it does in accounts. Colour carries meaning only: mint = money in / on track,
coral = money out / over, brass = focus and action.
"""
import html

BOTTLE, DEEP, PANEL = "#0A1F1B", "#071713", "#0E2823"
IVORY, SAGE, DIM = "#EFEBDD", "#9DB3A9", "#6F877D"
BRASS, MINT, CORAL = "#D9A441", "#7BD9A8", "#F08A7B"
HAIR = "rgba(239,235,221,.14)"

LEISURE_SHADES = ["#D9A441", "#E9C677", "#B98427", "#F1DDA8", "#9A6F1F"]
NEEDS_SHADES = ["#5FB3A1", "#7FB7D6", "#9AA8E0", "#B6A2D6", "#8FCFB0", "#6E9FB8", "#A9C7BD"]
NEUTRAL = "#6F877D"

FONTS = ("@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700"
         "&family=Newsreader:wght@400;500;600&display=swap');")

CSS = """
:root{
  --bottle:#0A1F1B; --deep:#071713; --panel:#0E2823; --raise:#12332C;
  --ivory:#EFEBDD; --sage:#9DB3A9; --dim:#6F877D;
  --brass:#D9A441; --mint:#7BD9A8; --coral:#F08A7B;
  --hair:rgba(239,235,221,.14); --hair2:rgba(239,235,221,.07);
  --serif:'Newsreader', Georgia, 'Times New Roman', serif;
  --sans:'Manrope', 'Segoe UI', system-ui, -apple-system, sans-serif;
}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"]{
  background:var(--bottle) !important; color:var(--ivory);
}
.stApp, .stApp :is(p,div,label,button,input,textarea,li,a,td,th,h4,h5,h6,small,summary,select),
.stApp span:not([data-testid="stIconMaterial"]):not([class*="material"]){
  font-family:var(--sans);
}
.stApp{ font-feature-settings:"tnum" 1, "lnum" 1; -webkit-font-smoothing:antialiased; }
[data-testid="stHeader"]{ background:transparent !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"], footer, #MainMenu, .stDeployButton{ display:none !important; }
.block-container{ max-width:1120px; padding:1.6rem 2rem 5rem; }

/* sidebar */
[data-testid="stSidebar"]{ background:var(--deep) !important; border-right:1px solid var(--hair2); }
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{ padding-top:.4rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3{
  font-family:var(--serif) !important; font-size:1.2rem !important; font-weight:500 !important;
  margin:1.4rem 0 .5rem !important; padding:0 !important; border:0 !important; color:var(--ivory);
}

/* headings: serif, ruled */
h1,h2,h3{ font-family:var(--serif) !important; font-weight:500 !important; letter-spacing:-.01em; color:var(--ivory); }
.block-container h3{ font-size:1.5rem !important; margin:2.4rem 0 .8rem !important; padding:0 0 .45rem !important; border-bottom:1px solid var(--hair); }
.block-container h4{ font-family:var(--serif) !important; font-weight:500; font-size:1.15rem; margin-top:1.4rem; }
[data-testid="stHeadingWithActionElements"] a, h1 a, h2 a, h3 a{ display:none !important; }
label p, [data-testid="stWidgetLabel"] p{ color:var(--sage) !important; font-size:.84rem !important; font-weight:600 !important; }
[data-testid="stCaptionContainer"], .stCaption, small{ color:var(--sage) !important; font-size:.84rem; line-height:1.5; }
hr{ border-color:var(--hair) !important; }

/* tabs */
[data-baseweb="tab-list"]{ gap:1.7rem; border-bottom:1px solid var(--hair); }
button[data-baseweb="tab"]{ background:transparent !important; padding:.65rem 0 !important; color:var(--sage) !important; font-weight:600; font-size:.93rem; }
button[data-baseweb="tab"] p{ color:inherit !important; font-weight:600; }
button[data-baseweb="tab"]:hover{ color:var(--ivory) !important; }
button[data-baseweb="tab"][aria-selected="true"]{ color:var(--ivory) !important; }
[data-baseweb="tab-highlight"]{ background:var(--brass) !important; height:2px !important; }
[data-baseweb="tab-border"]{ background:transparent !important; }

.stApp a, .stApp a:visited{ color:var(--brass) !important; text-decoration:none; }
.stApp a:hover{ text-decoration:underline; }
[data-testid="stSidebar"] .stButton{ margin:.5rem 0 .2rem; }

/* buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button, a[data-testid="stLinkButton"]{
  border-radius:6px; border:1px solid var(--hair); background:transparent; color:var(--ivory); font-weight:600;
  transition:border-color .15s ease, color .15s ease, background .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover{ border-color:var(--brass); color:var(--brass); background:transparent; }
[data-testid="stFormSubmitButton"] > button, .stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"]{
  background:var(--brass); border-color:var(--brass); color:#1b1405;
}
[data-testid="stFormSubmitButton"] > button:hover, .stButton > button[kind="primary"]:hover{ background:#E6B65A; color:#1b1405; border-color:#E6B65A; }
.stButton > button:disabled{ opacity:.4; }
.stButton > button[kind="primary"] p, [data-testid="stFormSubmitButton"] > button p, [data-testid="stBaseButton-primary"] p{ color:#1b1405 !important; font-weight:700; }

/* inputs */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"]{
  background:var(--panel) !important; border-radius:6px !important; border-color:var(--hair) !important;
}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within{ border-color:var(--brass) !important; }
input, textarea{ color:var(--ivory) !important; }
[data-testid="stNumberInput"] button{ background:transparent !important; }

/* forms, expanders */
[data-testid="stForm"]{ border:1px solid var(--hair) !important; border-radius:8px !important; background:rgba(14,40,35,.55); padding:1.1rem 1.2rem; }
[data-testid="stExpander"]{ border:1px solid var(--hair) !important; border-radius:8px !important; background:transparent; }
[data-testid="stExpander"] summary{ font-weight:600; color:var(--ivory); }

/* metrics that remain (goals, loans) */
[data-testid="stMetric"]{ border-top:1px solid var(--hair); padding:.7rem 0 .2rem; background:transparent; }
[data-testid="stMetricLabel"] p{ color:var(--sage) !important; font-size:.82rem !important; font-weight:600 !important; }
[data-testid="stMetricValue"]{ font-family:var(--serif) !important; font-weight:500 !important; font-size:1.85rem !important; letter-spacing:-.01em; }
[data-testid="stMetricValue"] *{ font-family:var(--serif) !important; }

/* tables */
[data-testid="stDataFrame"]{ border:1px solid var(--hair); border-radius:8px; overflow:hidden; }

/* native alerts, softened */
[data-testid="stAlert"]{ border-radius:6px !important; border:1px solid var(--hair) !important; background:rgba(239,235,221,.045) !important; color:var(--ivory) !important; }
[data-testid="stAlert"] p{ color:var(--ivory) !important; }

/* radios used as segmented choices */
[role="radiogroup"][aria-orientation="horizontal"], [data-testid="stRadio"] [role="radiogroup"]{ gap:.4rem 1.2rem; }

/* scrollbars */
::-webkit-scrollbar{ width:9px; height:9px; } ::-webkit-scrollbar-thumb{ background:rgba(239,235,221,.16); border-radius:6px; }
::-webkit-scrollbar-track{ background:transparent; }

/* ---------- ledger components ---------- */
.mast{ display:flex; justify-content:space-between; align-items:baseline; padding:.2rem 0 .8rem; margin-bottom:1.1rem; border-bottom:1px solid var(--hair); }
.mast .word{ font-family:var(--serif); font-size:1.5rem; font-weight:500; letter-spacing:-.01em; }
.mast .when{ color:var(--sage); font-size:.9rem; font-weight:500; }

.brand{ display:flex; align-items:center; gap:.65rem; padding:.9rem 0 .2rem; }
.brand svg{ flex:none; }
.brand .word{ font-family:var(--serif); font-size:1.45rem; font-weight:500; letter-spacing:-.01em; line-height:1; }
.brand .sub{ color:var(--dim); font-size:.74rem; margin-top:.2rem; }

.cap{ color:var(--sage); font-size:.84rem; font-weight:600; line-height:1.3; }
.note{ color:var(--sage); font-size:.84rem; line-height:1.4; }
.in{ color:var(--mint) !important; } .out{ color:var(--coral) !important; } .brass{ color:var(--brass) !important; }
.cur{ font-size:.5em; font-weight:500; margin-right:.22em; letter-spacing:.02em; color:var(--sage); vertical-align:.32em; }
.dec{ font-size:.58em; color:var(--sage); }

.hero{ display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); gap:2.4rem; align-items:end; padding:.8rem 0 1.6rem; }
.hero .fig{ display:inline-block; font-family:var(--serif); font-weight:500; font-size:clamp(2.7rem,6.4vw,4.5rem); line-height:1.02;
  letter-spacing:-.025em; margin:.45rem 0 .5rem; padding-bottom:.08em; border-bottom:5px double var(--brass); }
.hero .sub{ color:var(--sage); font-size:.95rem; }
.hero .sub b{ font-weight:700; }
.spark{ width:100%; height:auto; display:block; }
.spark text{ fill:var(--dim); font-size:11px; font-family:var(--sans); }

.strip{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border-top:1px solid var(--hair); border-bottom:1px solid var(--hair); margin:.4rem 0 1.2rem; }
.strip .cell{ padding:1.05rem 1.3rem 1.1rem; border-left:1px solid var(--hair); }
.strip .cell:first-child{ border-left:0; padding-left:0; }
.strip .num{ font-family:var(--serif); font-size:1.85rem; font-weight:500; letter-spacing:-.015em; margin:.3rem 0 .15rem; line-height:1.1; }
.strip .num .cur{ font-size:.55em; }

.rows{ margin:.2rem 0 .6rem; }
.rows .row{ display:grid; grid-template-columns:minmax(0,1fr) minmax(60px,150px) 150px; gap:1.1rem; align-items:center; padding:.8rem 0; border-bottom:1px solid var(--hair2); }
.rows .row.when{ grid-template-columns:64px minmax(0,1fr) 140px; }
.rows .row.plain{ grid-template-columns:minmax(0,1fr) auto; }
.rows .rl{ font-weight:600; font-size:.97rem; line-height:1.25; }
.rows .rl small{ display:block; color:var(--dim); font-size:.76rem; font-weight:500; margin-top:.15rem; }
.rows .amt{ font-family:var(--serif); font-size:1.15rem; font-weight:500; text-align:right; white-space:nowrap; letter-spacing:-.005em; }
.rows .date{ font-family:var(--serif); font-size:1.05rem; line-height:1.1; }
.rows .date small{ display:block; font-family:var(--sans); color:var(--dim); font-size:.72rem; margin-top:.15rem; }
.rows .row.total{ border-bottom:0; padding-top:.95rem; }
.rows .row.total .rl{ font-family:var(--serif); font-size:1.1rem; font-weight:500; }
.rows .row.total .amt{ font-size:1.35rem; display:inline-block; border-bottom:4px double var(--brass); padding-bottom:.05em; justify-self:end; }
.meter{ height:6px; background:var(--hair); border-radius:3px; overflow:hidden; }
.meter i{ display:block; height:100%; border-radius:3px; background:var(--sage); }
.meter i.ok{ background:var(--mint); } .meter i.warn{ background:var(--brass); } .meter i.bad{ background:var(--coral); }
.empty{ color:var(--sage); padding:1rem 0; border-bottom:1px solid var(--hair2); font-size:.95rem; }

.pools{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); border-top:1px solid var(--hair); border-bottom:1px solid var(--hair); margin:.6rem 0 1rem; }
.pool{ padding:1.15rem 1.4rem 1.3rem; border-left:1px solid var(--hair); }
.pool:first-child{ border-left:0; padding-left:0; }
.pool .big{ font-family:var(--serif); font-size:2.05rem; font-weight:500; letter-spacing:-.02em; margin:.35rem 0 .1rem; line-height:1.1; }
.pool .big .cur{ font-size:.5em; }
.pool .of{ color:var(--sage); font-size:.88rem; margin-bottom:.8rem; }
.pool .meter{ height:8px; border-radius:4px; }
.pool .status{ margin-top:.65rem; font-size:.88rem; font-weight:600; }

.bars .row{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(0,1.4fr) 120px 44px; gap:1rem; align-items:center; padding:.62rem 0; border-bottom:1px solid var(--hair2); }
.bars .nm{ font-weight:600; font-size:.94rem; } .bars .nm small{ color:var(--dim); font-weight:500; margin-left:.45rem; font-size:.74rem; }
.bars .v{ font-family:var(--serif); font-size:1.08rem; text-align:right; white-space:nowrap; }
.bars .sh{ color:var(--dim); font-size:.8rem; width:2.6rem; text-align:right; }
.bars .meter i.leis{ background:var(--brass); } .bars .meter i.need{ background:#5FB3A1; }

.notice{ border-left:3px solid var(--sage); padding:.7rem 1rem; margin:.6rem 0; background:rgba(239,235,221,.045); border-radius:0 6px 6px 0; font-size:.93rem; line-height:1.45; }
.notice.ok{ border-color:var(--mint); } .notice.warn{ border-color:var(--brass); } .notice.bad{ border-color:var(--coral); }

.goal{ padding:1.25rem 0 1.35rem; border-top:1px solid var(--hair); }
.goal .top{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem; }
.goal .nm{ font-family:var(--serif); font-size:1.5rem; font-weight:500; letter-spacing:-.01em; }
.goal .pc{ font-family:var(--serif); font-size:1.5rem; font-weight:500; color:var(--brass); }
.goal .meter{ height:8px; margin:.7rem 0 .75rem; border-radius:4px; } .goal .meter i{ background:var(--brass); }
.goal .line{ display:flex; flex-wrap:wrap; gap:.3rem 2rem; color:var(--sage); font-size:.9rem; }
.goal .line b{ color:var(--ivory); font-weight:600; font-family:var(--serif); font-size:1.02rem; }
.goal .verdict{ margin-top:.65rem; font-size:.92rem; }

.login{ max-width:380px; margin:7vh auto 1.2rem; }
.login .brand{ padding:0 0 1.4rem; } .login .brand .word{ font-size:2.1rem; }
.login h3{ border:0 !important; font-size:1.3rem !important; margin:0 0 .3rem !important; }

@media (max-width:760px){
  .block-container{ padding:1rem 1rem 4rem; }
  .hero{ grid-template-columns:1fr; gap:1rem; }
  .strip, .pools{ grid-template-columns:repeat(2,minmax(0,1fr)); }
  .strip .cell:nth-child(3), .pool:nth-child(3){ border-left:0; padding-left:0; }
  .strip .cell, .pool{ border-top:1px solid var(--hair2); }
  .bars .row{ grid-template-columns:minmax(0,1fr) auto; } .bars .row .meter, .bars .sh{ display:none; }
  .rows .row{ grid-template-columns:minmax(0,1fr) auto; } .rows .row .meter{ display:none; } .rows .row.total > div:nth-child(2){ display:none; }
  .rows .row.when{ grid-template-columns:56px minmax(0,1fr) auto; }
}
"""


def e(text):
    return html.escape(str(text), quote=True)


def inject(st):
    st.markdown(f"<style>{FONTS}{CSS}</style>", unsafe_allow_html=True)


def figure(x, cur="Rs", decimals=True):
    """Money as markup: small currency, large integer part, dimmed decimals. Negative values keep their minus sign."""
    sign = "&minus;" if x < 0 else ""
    whole, _, frac = f"{abs(x):,.2f}".partition(".")
    return f"{sign}<span class='cur'>{e(cur)}</span>{whole}" + (f"<span class='dec'>.{frac}</span>" if decimals else "")


def plain(x, cur="Rs"):
    return f"{'-' if x < 0 else ''}{cur} {abs(x):,.2f}"


def brand(sub="Personal accounts"):
    mark = ("<svg width='26' height='26' viewBox='0 0 24 24' fill='none' stroke='#D9A441' stroke-width='1.6' "
            "stroke-linecap='round'><rect x='3' y='3' width='18' height='18' rx='2.5'/><path d='M7 9h10M7 13h10M7 17h5'/></svg>")
    return (f"<div class='brand'>{mark}<div><div class='word'>Smart Ledger</div><div class='sub'>{e(sub)}</div></div></div>")


def masthead(when):
    return f"<div class='mast'><span class='word'>Smart Ledger</span><span class='when'>{e(when)}</span></div>"


LOGIN_CSS = ("<style>.block-container{max-width:440px !important;padding-top:10vh !important}"
             "[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],[data-testid='collapsedControl']{display:none !important}"
             ".login{margin:0 0 1rem !important;max-width:none !important}</style>")


def login_head(title, text):
    return (f"{LOGIN_CSS}<div class='login'>{brand('Personal accounts')}<h3>{e(title)}</h3>"
            f"<div class='note'>{e(text)}</div></div>")


def sparkline(values, labels, w=420, h=118):
    """Closing balance by month as a thin brass line with first and last labelled."""
    if not values:
        return ""
    pad_l, pad_r, pad_t, pad_b = 6, 10, 14, 26
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    xs = [pad_l + (w - pad_l - pad_r) * (i / (n - 1) if n > 1 else 0.5) for i in range(n)]
    ys = [pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / span) for v in values]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    base = h - pad_b + 6
    line = f"<polyline points='{pts}' fill='none' stroke='#D9A441' stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>" if n > 1 else ""
    dots = "".join(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{4 if i == n - 1 else 2.4}' fill='{'#D9A441' if i == n - 1 else '#0A1F1B'}' "
                   f"stroke='#D9A441' stroke-width='1.6'/>" for i, (x, y) in enumerate(zip(xs, ys)))
    first = f"<text x='{xs[0]:.1f}' y='{h - 6}' text-anchor='start'>{e(labels[0])}</text>"
    last = f"<text x='{xs[-1]:.1f}' y='{h - 6}' text-anchor='end'>{e(labels[-1])}</text>" if n > 1 else ""
    return (f"<svg class='spark' viewBox='0 0 {w} {h}' role='img' aria-label='Closing balance by month'>"
            f"<line x1='{pad_l}' x2='{w - pad_r}' y1='{base}' y2='{base}' stroke='rgba(239,235,221,.14)'/>{line}{dots}{first}{last}</svg>")


def hero(caption, value, sub_html, spark_svg=""):
    return (f"<div class='hero'><div><div class='cap'>{e(caption)}</div><div class='fig'>{figure(value)}</div>"
            f"<div class='sub'>{sub_html}</div></div><div>{spark_svg}</div></div>")


def strip(cells):
    """cells: [(caption, value, note, tone)] where tone is 'in', 'out', 'brass' or ''."""
    out = "".join(f"<div class='cell'><div class='cap'>{e(c)}</div><div class='num {t}'>{v}</div><div class='note'>{e(n)}</div></div>"
                  for c, v, n, t in cells)
    return f"<div class='strip'>{out}</div>"


def account_rows(items, total):
    """items: [(name, sub, balance)]. A neutral meter shows each account's share of what you hold."""
    top = max([b for _, _, b in items if b > 0] or [1.0])
    rows = ""
    for name, sub, bal in items:
        w = max(0.0, min(100.0, bal / top * 100)) if bal > 0 else 0
        s = f"<small>{e(sub)}</small>" if sub else ""
        rows += (f"<div class='row'><div class='rl'>{e(name)}{s}</div><div class='meter'><i style='width:{w:.0f}%'></i></div>"
                 f"<div class='amt {'out' if bal < 0 else ''}'>{figure(bal, decimals=True)}</div></div>")
    rows += f"<div class='row total'><div class='rl'>Total</div><div></div><div class='amt'>{figure(total)}</div></div>"
    return f"<div class='rows'>{rows}</div>"


def coming_rows(items):
    """items: [(date_label, days_label, title, kind, amount, tone)]; tone 'in' shows +, 'out' shows a minus, '' is neutral."""
    if not items:
        return ""
    rows = ""
    for d, when, title, kind, amt, tone in items:
        sign = "+" if tone == "in" else "&minus;" if tone == "out" else ""
        rows += (f"<div class='row when'><div class='date'>{e(d)}<small>{e(when)}</small></div>"
                 f"<div class='rl'>{e(title)}<small>{e(kind)}</small></div>"
                 f"<div class='amt {tone}'>{sign}{figure(abs(amt), decimals=True)}</div></div>")
    return f"<div class='rows'>{rows}</div>"


def pool(caption, spent, limit, cur="Rs", wide_note=""):
    over = spent > limit + 0.005
    ratio = (spent / limit) if limit > 0 else (1.0 if spent > 0 else 0.0)
    tone = "bad" if over else "warn" if ratio >= 0.8 else "ok"
    if limit <= 0:
        status, scls = ("No income recorded yet" if spent == 0 else f"{plain(spent, cur)} spent with no pool"), ""
    elif over:
        status, scls = f"Over by {plain(spent - limit, cur)}", "out"
    else:
        status, scls = f"{plain(limit - spent, cur)} left", "in" if tone == "ok" else "brass"
    return (f"<div class='pool'><div class='cap'>{e(caption)}</div><div class='big'>{figure(spent, cur)}</div>"
            f"<div class='of'>of {plain(limit, cur)}{(' ' + e(wide_note)) if wide_note else ''}</div>"
            f"<div class='meter'><i class='{tone}' style='width:{min(ratio, 1.0) * 100:.0f}%'></i></div>"
            f"<div class='status {scls}'>{status}</div></div>")


def pools(cells):
    return f"<div class='pools'>{''.join(cells)}</div>"


def bar_rows(items, empty="Nothing recorded yet."):
    """items: [(name, group, amount, share_percent, kind)] with kind 'leis' or 'need' for the bar colour."""
    if not items:
        return f"<div class='empty'>{e(empty)}</div>"
    top = max(a for _, _, a, _, _ in items) or 1.0
    rows = "".join(
        f"<div class='row'><div class='nm'>{e(n)}<small>{e(g)}</small></div>"
        f"<div class='meter'><i class='{k}' style='width:{a / top * 100:.0f}%'></i></div>"
        f"<div class='v'>{figure(a)}</div><div class='sh'>{s:.0f}%</div></div>" for n, g, a, s, k in items)
    return f"<div class='bars'>{rows}</div>"


def notice(kind, text):
    return f"<div class='notice {kind}'>{e(text)}</div>"


def goal(name, percent, saved, target, left, counts, verdict_html=""):
    return (f"<div class='goal'><div class='top'><div class='nm'>{e(name)}</div><div class='pc'>{percent:.0f}%</div></div>"
            f"<div class='meter'><i style='width:{min(max(percent, 0), 100):.0f}%'></i></div>"
            f"<div class='line'><span>Saved <b>{plain(saved)}</b></span><span>Target <b>{plain(target)}</b></span>"
            f"<span>To go <b>{plain(left)}</b></span><span>{e(counts)}</span></div>"
            f"{('<div class=verdict>' + verdict_html + '</div>') if verdict_html else ''}</div>")


def style_fig(fig, height=300, legend=True):
    """Make a Plotly figure match the page: transparent, hairline grid, Manrope text, ledger colours."""
    fig.update_layout(
        height=height, margin=dict(t=8, b=8, l=6, r=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Manrope, Segoe UI, system-ui, sans-serif", color=SAGE, size=12),
        colorway=[BRASS, MINT, "#5FB3A1", CORAL, "#9AA8E0", "#B6A2D6"],
        legend=dict(orientation="h", y=1.12, x=0, title_text="", font=dict(size=12, color=IVORY)) if legend else None,
        showlegend=legend, hoverlabel=dict(bgcolor="#12332C", bordercolor="rgba(239,235,221,.2)", font=dict(color=IVORY, size=12)),
        bargap=0.42, bargroupgap=0.06)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="rgba(239,235,221,.2)", tickfont=dict(color=SAGE))
    fig.update_yaxes(gridcolor="rgba(239,235,221,.08)", zeroline=False, tickfont=dict(color=SAGE), title_text="")
    try:
        fig.update_traces(marker_cornerradius=3, selector=dict(type="bar"))
    except Exception:
        pass
    return fig
