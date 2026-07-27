#!/usr/bin/env python3
"""
讀取 data/prices.json，組成一則原物料日報，透過 Telegram Bot 發送出去。

需要的環境變數：
  TELEGRAM_BOT_TOKEN  - 用 @BotFather 建立機器人後拿到的 token
  TELEGRAM_CHAT_ID    - 要發送到的對象，可以是：
                          - 你個人的 chat id（純數字）
                          - 群組的 chat id（負數，例如 -1001234567890）
                          - 公開頻道的 @使用者名稱（例如 @your_channel）
                        可以同時發給多個對象，中間用逗號分隔，例如：
                          "123456789,-1001234567890,@your_channel"
  DASHBOARD_URL       - （選填）你的 GitHub Pages 網址，會附在訊息最後面

沒有設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 時，這個腳本會直接跳過、
不會讓整個 workflow 失敗（方便你還沒設定 Telegram 之前，價格更新照常運作）。
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

DATA_PATH = os.path.join(os.path.dirname(__file__), "prices.json")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS_RAW = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()


def fmt(v, dec):
    return f"{v:,.{dec}f}"


def pct_change(new, old):
    if old in (None, 0):
        return None
    return (new - old) / old * 100


def arrow(change):
    if change is None:
        return ""
    return "📈" if change >= 0 else "📉"


def build_message(data):
    labels = data["labels"]
    oil = data["oil"][-1]
    copper = data["copper"][-1]
    gold = data["gold"][-1]

    prev = data.get("previous_snapshot", {})
    oil_chg = pct_change(oil, prev.get("oil"))
    copper_chg = pct_change(copper, prev.get("copper"))
    gold_chg = pct_change(gold, prev.get("gold"))

    today_taipei = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d")

    def line(emoji, name, value, dec, unit, chg):
        chg_txt = f" ({arrow(chg)} {abs(chg):.2f}%)" if chg is not None else ""
        return f"{emoji} {name}：<b>${fmt(value, dec)}</b> {unit}{chg_txt}"

    lines = [
        f"📊 <b>原物料每日快報</b> — {today_taipei}（台北時間）",
        "",
        line("🛢️", "原油 WTI", oil, 2, "/桶", oil_chg),
        line("🟫", "銅 LME", copper, 0, "/公噸", copper_chg),
        line("🟡", "黃金 XAU", gold, 2, "/盎司", gold_chg),
    ]

    if DASHBOARD_URL:
        lines += ["", f"完整走勢圖：{DASHBOARD_URL}"]

    return "\n".join(lines)


def send_to(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if not body.get("ok", False):
            print(f"  ✗ 發送到 {chat_id} 失敗：{body}")
            return False
        print(f"  ✓ 已發送到 {chat_id}")
        return True
    except Exception as e:
        print(f"  ✗ 發送到 {chat_id} 時發生錯誤：{e}")
        return False


def main():
    if not BOT_TOKEN or not CHAT_IDS_RAW:
        print("尚未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，略過通知步驟。")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    text = build_message(data)
    print("準備發送以下訊息：\n" + text + "\n")

    chat_ids = [c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip()]
    ok_count = 0
    for cid in chat_ids:
        if send_to(cid, text):
            ok_count += 1

    if ok_count == 0:
        print("所有對象都發送失敗。")
        sys.exit(1)


if __name__ == "__main__":
    main()
