"""Excel export for Smart Ledger.

Builds a workbook whose totals are live formulas (SUMIFS over the Transactions sheet), so you can edit or add rows in
Excel and everything recalculates. Cached values are stored too, so previews and phone viewers show numbers.
Colour code: blue text = a number you may change; black = a formula; green = link to another sheet.
"""
import io

import pandas as pd

try:
    import xlsxwriter
    from xlsxwriter.utility import xl_col_to_name
except ImportError:                                    # the app shows a friendly message
    xlsxwriter = None

MONEY = '#,##0.00;(#,##0.00);"-"'
FONT = "Arial"


def build_workbook(tx, accounts, summary, cats, goals, loan_rows, settings, currency="Rs", account_cols=None):
    if xlsxwriter is None:
        raise RuntimeError("The xlsxwriter package is missing. Run:  pip install xlsxwriter")
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "default_date_format": "dd mmm yyyy"})
    wb.set_calc_mode("auto")

    def fmt(**kw):
        base = {"font_name": FONT, "font_size": 10, "valign": "vcenter"}
        base.update(kw)
        return wb.add_format(base)

    f_title = fmt(bold=True, font_size=15, font_color="#0A1F1B")
    f_note = fmt(italic=True, font_color="#5B6B64")
    f_head = fmt(bold=True, font_color="#EFEBDD", bg_color="#0A1F1B", align="center", border=1, border_color="#0A1F1B", text_wrap=True)
    f_head_l = fmt(bold=True, font_color="#EFEBDD", bg_color="#0A1F1B", align="left", border=1, border_color="#0A1F1B")
    f_text = fmt(bottom=1, bottom_color="#E3E7E4")
    f_money = fmt(num_format=MONEY, bottom=1, bottom_color="#E3E7E4")
    f_pct = fmt(num_format="0.0%", bottom=1, bottom_color="#E3E7E4")
    f_date = fmt(num_format="dd mmm yyyy", align="left", bottom=1, bottom_color="#E3E7E4")
    f_int = fmt(num_format="0", align="center", bottom=1, bottom_color="#E3E7E4")
    f_in_money = fmt(num_format=MONEY, font_color="#0000FF", bottom=1, bottom_color="#E3E7E4")
    f_in_pct = fmt(num_format="0.0%", font_color="#0000FF", bg_color="#FFF8E1", border=1, border_color="#D9A441")
    f_in_text = fmt(font_color="#0000FF", align="center", bottom=1, bottom_color="#E3E7E4")
    f_link = fmt(num_format=MONEY, font_color="#007A33", bottom=1, bottom_color="#E3E7E4")
    f_label = fmt(bold=True)
    f_tot_l = fmt(bold=True, top=1, bottom=6)
    f_tot = fmt(bold=True, num_format=MONEY, top=1, bottom=6)
    f_tot_pct = fmt(bold=True, num_format="0.0%", top=1, bottom=6)

    ws = wb.add_worksheet("Summary")
    ws_t = wb.add_worksheet("Transactions")
    wc = wb.add_worksheet("By category")
    wbud = wb.add_worksheet("Budget")
    wg = wb.add_worksheet("Goals and loans")

    n = len(tx)
    last = max(n + 1 + 2000, 2000)                    # leave room for rows you add by hand
    T = lambda col: f"Transactions!${col}$2:${col}${last}"        # noqa: E731

    months = summary["Month"].tolist()
    acc_cols = account_cols or accounts["name"].tolist()
    opening = dict(zip(accounts["name"], accounts["opening_balance"]))

    # ------------------------------------------------------------------ Transactions
    heads = ["No.", "Date", "Type", "Category", "Account", "To account", "Amount", "Notes", "Month"]
    for c, h in enumerate(heads):
        ws_t.write(0, c, h, f_head)
    tx_sorted = tx.sort_values(["date", "id"]).reset_index(drop=True)
    for i, r in tx_sorted.iterrows():
        row = i + 1
        ws_t.write_number(row, 0, i + 1, f_int)
        ws_t.write_datetime(row, 1, r["date"].to_pydatetime(), f_date)
        ws_t.write(row, 2, r["type"], f_text)
        ws_t.write(row, 3, r["category"] if isinstance(r["category"], str) else "", f_text)
        ws_t.write(row, 4, r["account"], f_text)
        ws_t.write(row, 5, r["to_account"] if isinstance(r["to_account"], str) else "", f_text)
        ws_t.write_number(row, 6, float(r["amount"]), f_money)
        ws_t.write(row, 7, r["description"] if isinstance(r["description"], str) else "", f_text)
        ws_t.write_formula(row, 8, f'=TEXT(B{row + 1},"yyyy-mm")', f_text, r["date"].strftime("%Y-%m"))
    for c, w in enumerate([6, 13, 10, 28, 18, 18, 14, 42, 10]):
        ws_t.set_column(c, c, w)
    ws_t.freeze_panes(1, 0)
    ws_t.autofilter(0, 0, max(n, 1), len(heads) - 1)

    # ------------------------------------------------------------------ Summary
    ws.write("A1", "Smart Ledger: month by month", f_title)
    ws.write("A2", f"Amounts in {currency}. Blue = a number you can change. Black = a formula. Green = linked from another sheet.", f_note)
    ws.write("A4", "Save at least (% of income)", f_label)
    ws.write_number("B4", settings["save_min"] / 100, f_in_pct)
    ws.write("A5", "Leisure pool (% of income)", f_label)
    ws.write_number("B5", settings["leisure_pct"] / 100, f_in_pct)
    ws.write("A6", "Everything else (% of income)", f_label)
    ws.write_formula("B6", "=1-B4-B5", fmt(num_format="0.0%"), 1 - settings["save_min"] / 100 - settings["leisure_pct"] / 100)

    HEAD, FIRST = 8, 9                                  # 1-based rows: header row 8, first month row 9, opening balances row 7
    base_heads = ["Month", "Month end", "Opening", "Money in", "Money out", "Closing", "Saved", "Savings rate"]
    first_acc = len(base_heads)
    ws.write(6, 0, "Opening balance of each account", f_note)
    for c, h in enumerate(base_heads):
        ws.write(HEAD - 1, c, h, f_head if c else f_head_l)
    for j, a in enumerate(acc_cols):
        ws.write_number(6, first_acc + j, float(opening.get(a, 0.0)), f_in_money)
        ws.write(HEAD - 1, first_acc + j, a, f_head)
    check_col = first_acc + len(acc_cols)
    ws.write(HEAD - 1, check_col, "Check (should be 0)", f_head)

    for i, m in enumerate(months):
        r = FIRST + i                                    # 1-based sheet row
        srow = summary.iloc[i]
        month_end = (pd.Period(m).end_time).normalize().to_pydatetime()
        ws.write(r - 1, 0, m, f_text)
        ws.write_datetime(r - 1, 1, month_end, f_date)
        if i == 0:
            ws.write_formula(r - 1, 2, f"=SUM({xl_col_to_name(first_acc)}7:{xl_col_to_name(check_col - 1)}7)", f_money, float(srow["Opening"]))
        else:
            ws.write_formula(r - 1, 2, f"=F{r - 1}", f_money, float(srow["Opening"]))
        ws.write_formula(r - 1, 3, f'=SUMIFS({T("G")},{T("C")},"Inflow",{T("I")},$A{r})', f_money, float(srow["Inflows"]))
        ws.write_formula(r - 1, 4, f'=SUMIFS({T("G")},{T("C")},"Outflow",{T("I")},$A{r})', f_money, float(srow["Outflows"]))
        ws.write_formula(r - 1, 5, f"=C{r}+D{r}-E{r}", f_money, float(srow["Closing"]))
        saved = float(srow["Inflows"] - srow["Outflows"])
        ws.write_formula(r - 1, 6, f"=D{r}-E{r}", f_money, saved)
        ws.write_formula(r - 1, 7, f"=IF(D{r}=0,0,G{r}/D{r})", f_pct, saved / float(srow["Inflows"]) if srow["Inflows"] else 0.0)
        for j, a in enumerate(acc_cols):
            col = xl_col_to_name(first_acc + j)
            hdr = f"{col}${HEAD}"
            fml = (f'={col}$7+SUMIFS({T("G")},{T("C")},"Inflow",{T("E")},{hdr},{T("B")},"<="&$B{r})'
                   f'-SUMIFS({T("G")},{T("C")},"Outflow",{T("E")},{hdr},{T("B")},"<="&$B{r})'
                   f'-SUMIFS({T("G")},{T("C")},"Transfer",{T("E")},{hdr},{T("B")},"<="&$B{r})'
                   f'+SUMIFS({T("G")},{T("C")},"Transfer",{T("F")},{hdr},{T("B")},"<="&$B{r})')
            ws.write_formula(r - 1, first_acc + j, fml, f_money, float(srow[a]))
        ws.write_formula(r - 1, check_col,
                         f"=ROUND(F{r}-SUM({xl_col_to_name(first_acc)}{r}:{xl_col_to_name(check_col - 1)}{r}),2)", f_money, 0.0)
    lastm = FIRST + len(months) - 1
    tr = lastm + 1                                      # totals row (1-based)
    ws.write(tr - 1, 0, "Total", f_tot_l)
    for c in (1, 2, 5):
        ws.write_blank(tr - 1, c, None, f_tot_l)
    ws.write_formula(tr - 1, 3, f"=SUM(D{FIRST}:D{lastm})", f_tot, float(summary["Inflows"].sum()))
    ws.write_formula(tr - 1, 4, f"=SUM(E{FIRST}:E{lastm})", f_tot, float(summary["Outflows"].sum()))
    tot_saved = float(summary["Inflows"].sum() - summary["Outflows"].sum())
    ws.write_formula(tr - 1, 6, f"=D{tr}-E{tr}", f_tot, tot_saved)
    ws.write_formula(tr - 1, 7, f"=IF(D{tr}=0,0,G{tr}/D{tr})", f_tot_pct, tot_saved / float(summary["Inflows"].sum()) if summary["Inflows"].sum() else 0.0)
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 13)
    ws.set_column(2, 7, 14)
    ws.set_column(first_acc, check_col, 16)
    ws.set_row(HEAD - 1, 30)
    ws.freeze_panes(HEAD, 1)

    if len(months) >= 1:
        ch = wb.add_chart({"type": "column"})
        ch.add_series({"name": "Money in", "categories": ["Summary", FIRST - 1, 0, lastm - 1, 0],
                       "values": ["Summary", FIRST - 1, 3, lastm - 1, 3], "fill": {"color": "#3E9B72"}, "gap": 80})
        ch.add_series({"name": "Money out", "categories": ["Summary", FIRST - 1, 0, lastm - 1, 0],
                       "values": ["Summary", FIRST - 1, 4, lastm - 1, 4], "fill": {"color": "#D4705F"}})
        ln = wb.add_chart({"type": "line"})
        ln.add_series({"name": "Closing balance", "categories": ["Summary", FIRST - 1, 0, lastm - 1, 0],
                       "values": ["Summary", FIRST - 1, 5, lastm - 1, 5], "y2_axis": True,
                       "line": {"color": "#D9A441", "width": 2.25}, "marker": {"type": "circle", "size": 6,
                                                                                "fill": {"color": "#D9A441"}, "border": {"color": "#D9A441"}}})
        ch.combine(ln)
        ch.set_title({"name": "Money in, money out and closing balance", "name_font": {"name": FONT, "size": 11}})
        ch.set_legend({"position": "bottom"})
        ch.set_y_axis({"num_format": "#,##0", "major_gridlines": {"visible": True, "line": {"color": "#E3E7E4"}}})
        ln.set_y2_axis({"num_format": "#,##0"})
        ch.set_size({"width": 760, "height": 300})
        ws.insert_chart(tr + 2, 0, ch)

    # ------------------------------------------------------------------ By category
    wc.write("A1", "Spending and income by category", f_title)
    wc.write("A2", "Each cell is a SUMIFS over the Transactions sheet. Change a group in row 5 (Leisure or Everything else) and the Budget sheet follows.", f_note)
    leis = set(cats.loc[cats["is_leisure"] == 1, "name"])
    out_cats = [c for c in cats.loc[cats["type"] == "Outflow", "name"] if (tx[(tx["type"] == "Outflow") & (tx["category"] == c)]["amount"].sum() != 0)]
    in_cats = [c for c in cats.loc[cats["type"] == "Inflow", "name"] if (tx[(tx["type"] == "Inflow") & (tx["category"] == c)]["amount"].sum() != 0)]

    out_cats = out_cats or ["(none yet)"]               # keeps every formula valid when a block would be empty
    in_cats = in_cats or ["(none yet)"]

    def block(top, kind, names, with_group):
        """Writes one block; returns (first_data_row, last_data_row) as 1-based sheet rows."""
        label = "Money out by category" if kind == "Outflow" else "Money in by category"
        wc.write(top - 1, 0, label, f_label)
        hdr_row = top + 2 if with_group else top + 1
        if with_group:
            wc.write(top, 0, "Group", f_note)
        wc.write(hdr_row - 1, 0, "Month", f_head_l)
        for j, nm in enumerate(names):
            wc.write(hdr_row - 1, 1 + j, nm, f_head)
            if with_group:
                wc.write(top, 1 + j, "Leisure" if nm in leis else "Everything else", f_in_text)
        wc.write(hdr_row - 1, 1 + len(names), "Total", f_head)
        first = hdr_row + 1
        for i, m in enumerate(months):
            r = first + i
            wc.write(r - 1, 0, m, f_text)
            tot = 0.0
            for j, nm in enumerate(names):
                col = xl_col_to_name(1 + j)
                v = float(tx[(tx["type"] == kind) & (tx["category"] == nm) & (tx["date"].dt.strftime("%Y-%m") == m)]["amount"].sum())
                tot += v
                wc.write_formula(r - 1, 1 + j, f'=SUMIFS({T("G")},{T("C")},"{kind}",{T("D")},{col}${hdr_row},{T("I")},$A{r})', f_money, v)
            wc.write_formula(r - 1, 1 + len(names), f"=SUM(B{r}:{xl_col_to_name(len(names))}{r})", f_money, tot)
        lastr = first + len(months) - 1
        tr_ = lastr + 1
        wc.write(tr_ - 1, 0, "Total", f_tot_l)
        for j, nm in enumerate(names + ["Total"]):
            col = xl_col_to_name(1 + j)
            v = float(tx[(tx["type"] == kind) & ((tx["category"] == nm) if nm != "Total" else True)]["amount"].sum())
            wc.write_formula(tr_ - 1, 1 + j, f"=SUM({col}{first}:{col}{lastr})", f_tot, v)
        return first, lastr, hdr_row

    o_first, o_last, o_hdr = block(4, "Outflow", out_cats, True)
    i_first, i_last, _ = block(o_last + 4, "Inflow", in_cats, False)
    wc.set_column(0, 0, 14)
    wc.set_column(1, max(len(out_cats), len(in_cats)) + 1, 17)
    wc.set_row(o_hdr - 1, 30)
    wc.freeze_panes(0, 1)
    grp_row = 5                                          # 1-based row holding the Group labels
    last_col_name = xl_col_to_name(len(out_cats))

    # ------------------------------------------------------------------ Budget
    wbud.write("A1", "Budget pools by month", f_title)
    wbud.write("A2", "Pools are a share of that month's money in; the shares come from Summary B4:B6. Positive = left, negative = over.", f_note)
    heads_b = ["Month", "Money in", "Savings target", "Saved", "Saved minus target", "Leisure pool", "Leisure spent",
               "Leisure left", "Everything else pool", "Everything else spent", "Everything else left"]
    for c, h in enumerate(heads_b):
        wbud.write(3, c, h, f_head if c else f_head_l)
    wbud.set_row(3, 32)
    sm = lambda col: f"Summary!${col}${FIRST}:${col}${lastm}"                       # noqa: E731
    cat_rng = f"'By category'!$B${o_first}:${last_col_name}${o_last}"
    cat_mon = f"'By category'!$A${o_first}:$A${o_last}"
    grp_rng = f"'By category'!$B${grp_row}:${last_col_name}${grp_row}"
    for i, m in enumerate(months):
        r = 5 + i
        s = summary.iloc[i]
        inc, out = float(s["Inflows"]), float(s["Outflows"])
        saved = inc - out
        leis_spent = float(tx[(tx["type"] == "Outflow") & (tx["category"].isin(leis)) & (tx["date"].dt.strftime("%Y-%m") == m)]["amount"].sum())
        lp, sp = settings["leisure_pct"] / 100, settings["save_min"] / 100
        ep = 1 - sp - lp
        wbud.write(r - 1, 0, m, f_text)
        wbud.write_formula(r - 1, 1, f"=INDEX({sm('D')},MATCH($A{r},{sm('A')},0))", f_link, inc)
        wbud.write_formula(r - 1, 2, f"=B{r}*Summary!$B$4", f_money, inc * sp)
        wbud.write_formula(r - 1, 3, f"=INDEX({sm('G')},MATCH($A{r},{sm('A')},0))", f_link, saved)
        wbud.write_formula(r - 1, 4, f"=D{r}-C{r}", f_money, saved - inc * sp)
        wbud.write_formula(r - 1, 5, f"=B{r}*Summary!$B$5", f_money, inc * lp)
        if out_cats:
            wbud.write_formula(r - 1, 6, f'=SUMIF({grp_rng},"Leisure",INDEX({cat_rng},MATCH($A{r},{cat_mon},0),0))', f_money, leis_spent)
        else:
            wbud.write_number(r - 1, 6, 0.0, f_money)
        wbud.write_formula(r - 1, 7, f"=F{r}-G{r}", f_money, inc * lp - leis_spent)
        wbud.write_formula(r - 1, 8, f"=B{r}*Summary!$B$6", f_money, inc * ep)
        wbud.write_formula(r - 1, 9, f"=INDEX({sm('E')},MATCH($A{r},{sm('A')},0))-G{r}", f_money, out - leis_spent)
        wbud.write_formula(r - 1, 10, f"=I{r}-J{r}", f_money, inc * ep - (out - leis_spent))
    red = wb.add_format({"font_color": "#C0392B"})
    green = wb.add_format({"font_color": "#1E8449"})
    for col in ("E", "H", "K"):
        rng = f"{col}5:{col}{4 + len(months)}"
        wbud.conditional_format(rng, {"type": "cell", "criteria": "<", "value": 0, "format": red})
        wbud.conditional_format(rng, {"type": "cell", "criteria": ">=", "value": 0, "format": green})
    wbud.set_column(0, 0, 12)
    wbud.set_column(1, 10, 16)
    wbud.freeze_panes(4, 1)

    # ------------------------------------------------------------------ Goals & loans
    wg.write("A1", "Savings goals and loans", f_title)
    wg.write("A2", "Saved, paid back and similar figures are a snapshot taken when this file was exported.", f_note)
    gh = ["Goal", "Target", "Saved", "To go", "Done", "Deadline", "Counts these accounts"]
    for c, h in enumerate(gh):
        wg.write(3, c, h, f_head if c else f_head_l)
    row = 5
    for g in goals.itertuples():
        wg.write(row - 1, 0, g.name, f_text)
        wg.write_number(row - 1, 1, float(g.target), f_in_money)
        wg.write_number(row - 1, 2, float(g.saved_now), f_in_money)
        wg.write_formula(row - 1, 3, f"=MAX(B{row}-C{row},0)", f_money, max(float(g.target) - float(g.saved_now), 0))
        wg.write_formula(row - 1, 4, f"=IF(B{row}=0,0,C{row}/B{row})", f_pct, float(g.saved_now) / float(g.target) if g.target else 0.0)
        wg.write(row - 1, 5, g.deadline if isinstance(g.deadline, str) and g.deadline else "none", f_text)
        wg.write(row - 1, 6, g.accounts, f_text)
        row += 1
    if goals.empty:
        wg.write(row - 1, 0, "No goals yet.", f_note)
        row += 1
    row += 2
    lh = ["Person", "Direction", "Original", "Paid back", "Written off", "Outstanding", "Due", "Status"]
    for c, h in enumerate(lh):
        wg.write(row - 1, c, h, f_head if c else f_head_l)
    row += 1
    for r in loan_rows:
        wg.write(row - 1, 0, r["Person"], f_text)
        wg.write(row - 1, 1, r["Type"], f_text)
        wg.write_number(row - 1, 2, float(r["Original"]), f_in_money)
        wg.write_number(row - 1, 3, float(r["Paid back"]), f_in_money)
        wg.write_number(row - 1, 4, float(r["Written off"]), f_in_money)
        wg.write_formula(row - 1, 5, f"=C{row}-D{row}-E{row}", f_money, float(r["Outstanding"]))
        wg.write(row - 1, 6, r["Due"] or "none", f_text)
        wg.write(row - 1, 7, r["Status"], f_text)
        row += 1
    if not loan_rows:
        wg.write(row - 1, 0, "No loans recorded.", f_note)
    wg.set_column(0, 0, 24)
    wg.set_column(1, 7, 17)
    wg.set_column(6, 6, 30)

    for sheet in (ws, wc, wbud, wg, ws_t):
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.hide_gridlines(2)
    ws_t.hide_gridlines(0)
    wb.set_properties({"title": "Smart Ledger export", "subject": "Personal accounts", "comments": "Generated by Smart Ledger"})
    ws.activate()
    wb.close()
    return buf.getvalue()
