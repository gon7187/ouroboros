    spent = float(st.get("spent_usd") or 0.0)
    pct = budget_pct(st)
    if TOTAL_BUDGET_LIMIT > 0:
        budget_remaining_usd = max(0, TOTAL_BUDGET_LIMIT - spent)
        lines.append(f"budget_total: ${TOTAL_BUDGET_LIMIT:.0f}")
        lines.append(f"budget_remaining: ${budget_remaining_usd:.0f}")
    if pct > 0:
        lines.append(f"spent_usd: ${spent:.2f} ({pct:.1f}% of budget)")
    else:
        lines.append(f"spent_usd: ${spent:.2f}")