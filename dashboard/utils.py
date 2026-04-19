def fmt_money(value: float, symbol: str = "") -> str:
    """Abrevia números grandes. 1,962,605 → 1.96M"""
    prefix = f"{symbol} " if symbol else ""
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        return f"{prefix}{value / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"{prefix}{value / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"{prefix}{value / 1_000:.1f}K"
    return f"{prefix}{value:.0f}"


def fmt_table(df, money_cols: list[str], symbol: str = ""):
    """Formatea columnas de dinero en un DataFrame para mostrar en tabla."""
    df = df.copy()
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: fmt_money(v, symbol))
    return df
