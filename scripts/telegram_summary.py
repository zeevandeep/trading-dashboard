"""Build a daily Telegram summary from live equity CSVs and send it."""
import csv
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_last_two(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return None, None
    return (rows[-2] if len(rows) > 1 else None), rows[-1]


def fmt_pct(val):
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def nav_return_pct(nav: float) -> float:
    """NAV is stored as a multiplier (1.0 = 0%, 1.05 = +5%). Return % change."""
    return (nav - 1.0) * 100


def build_message():
    lines = ["📊 *JD Quant Daily Update*", ""]
    mark_date = None

    strategies = [
        ("Ascent", "data/live/smallcap_momentum_v2_live/equity.csv"),
        ("Bedrock", "data/live/value_quality_v1_live/equity.csv"),
    ]

    for name, rel_path in strategies:
        path = ROOT / rel_path
        if not path.exists():
            lines.append(f"*{name}*: no data")
            continue

        prev, last = read_last_two(str(path))
        if not last:
            lines.append(f"*{name}*: empty")
            continue

        mark_date = last.get("date", "")
        nav = float(last.get("nav", 1.0))
        mv = float(last.get("market_value", 0))
        inv = float(last.get("invested", 0))
        pnl = float(last.get("pnl", 0))
        n_pos = int(last.get("n_positions", 0))
        total_ret = nav_return_pct(nav)

        daily_str = ""
        if prev:
            prev_nav = float(prev.get("nav", nav))
            daily_ret = (nav / prev_nav - 1) * 100 if prev_nav > 0 else 0
            daily_str = f"  ({fmt_pct(daily_ret)} today)"

        lines.append(
            f"*{name}*: NAV {fmt_pct(total_ret)}{daily_str}"
            f"\n  ₹{mv:,.0f} market · ₹{pnl:+,.0f} P&L · {n_pos} pos"
        )

    # ── Trend filter comparison (Ascent vs Ascent+filter) ────────────────────
    tf_path = ROOT / "data/paper/ascent_trend_filtered/equity.csv"
    if tf_path.exists():
        _, tf_last = read_last_two(str(tf_path))
        if tf_last:
            tf_nav = float(tf_last.get("nav", 1.0))
            tf_ret = nav_return_pct(tf_nav)
            regime = tf_last.get("regime", "UNKNOWN")
            nifty_10m = float(tf_last.get("nifty_10m_ret", 0))
            regime_icon = "🟢" if regime == "RISK_ON" else "🔴"
            lines.append(
                f"\n*Trend Filter* (paper): NAV {fmt_pct(tf_ret)}"
                f"\n  {regime_icon} {regime} · NIFTY 10m {fmt_pct(nifty_10m)}"
            )

    if mark_date:
        lines.append(f"\n_{mark_date}_")

    return "\n".join(lines)


def send(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req)
    print("Telegram message sent.")


if __name__ == "__main__":
    msg = build_message()
    print(msg)
    send(msg)
