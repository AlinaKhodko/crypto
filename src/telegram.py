import os, requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

def _tg_escape_md2(text: str) -> str:
    # Escape MarkdownV2 reserved chars
    for ch in r'_\*\[\]\(\)~`>#+-=|{}.!':
        text = text.replace(ch, f"\\{ch}")
    return text

def notify_telegram(datetime_, sname, operation, ma_level):
    if not (BOT_TOKEN and CHAT_ID):
        return  # quietly skip if not configured

    if operation.upper() == "BUY":
        op_display = "🟢 BUY 🚀"
    else:
        op_display = "🔴 SELL 💥"

    msg = f"{op_display} {sname} {datetime_:%Y-%m-%d %H:%M} @ {ma_level}"
    print(msg)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg
        }, timeout=10).raise_for_status()
    except Exception as e:
        # Don't crash your pipeline on Telegram issues
        print(f"[telegram] warn: {e}")

