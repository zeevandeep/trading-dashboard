"""Build a daily Telegram summary from equity CSVs and send it."""
import csv
import os
import sys
import urllib.request
import urllib.parse

def read_last_two(path):
    """Return (prev_row, last_row) or (None, last_row) from a CSV."""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return None, None
    if len(rows) == 1:
        return None, rows[-1]
    return rows[-2], rows[-1]

def fmt_pct(val):
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"

def build_message():
    lines = ["📊 *JD Quant Daily Mark*", ""]

    # Paper: Ascent
    ascent_path = "data/paper/smallcap_momentum_v2/equity.csv"
    if os.path.exists(ascent_path):
        prev, last = read_last_two(ascent_path)
        if last:
            equity = float(last["equity"])
            total_ret = (equity - 1) * 100
            daily = ""
            if prev:
                daily_ret = (float(last["equity"]) / float(prev["equity"]) - 1) * 100
                daily = f" ({fmt_pct(daily_ret)} today)"
            lines.append(f"*Ascent* (paper): {fmt_pct(total_ret)} total{daily}")

    # Paper: Bedrock
    bedrock_path = "data/paper/value_quality_v1/equity.csv"
    if os.path.exists(bedrock_path):
        prev, last = read_last_two(bedrock_path)
        if last:
            equity = float(last["equity"])
            total_ret = (equity - 1) * 100
            daily = ""
            if prev:
                daily_ret = (float(last["equity"]) / float(prev["equity"]) - 1) * 100
                daily = f" ({fmt_pct(daily_ret)} today)"
            lines.append(f"*Bedrock* (paper): {fmt_pct(total_ret)} total{daily}")

    # Live
    live_path = "data/live/smallcap_momentum_v2_live/equity.csv"
    if os.path.exists(live_path):
        prev, last = read_last_two(live_path)
        if last:
            pnl = float(last["pnl"])
            pnl_pct = float(last["pnl_pct"])
            lines.append(f"*Live* (₹10K): ₹{pnl:+,.0f} ({fmt_pct(pnl_pct)})")

    lines.append(f"\n_{last['date'] if last else 'N/A'}_")
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
