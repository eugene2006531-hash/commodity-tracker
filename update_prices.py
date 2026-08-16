#!/usr/bin/env python3
"""
每日更新 prices.json：
  - 原油 WTI：美國 EIA 官方 API（series PET.RWTC.D，每日現貨價）
  - 銅：FRED（美國聖路易斯聯邦儲備銀行）官方資料庫，series PCOPPUSDM，
    來源是 IMF，單位明確是 USD/公噸（月度資料，免費、無付費牆）
  - 黃金：MetalpriceAPI（api.metalpriceapi.com），免費方案，單位 USD/盎司

需要的環境變數（由 GitHub Actions secrets 注入）：
  EIA_API_KEY      - 到 https://www.eia.gov/opendata/register.php 免費申請
  FRED_API_KEY     - 到 https://fredaccount.stlouisfed.org/apikeys 免費申請
  METALS_API_KEY   - 到 https://metalpriceapi.com/register 免費申請

設計邏輯：
  - 若目前月份（YYYY-MM）已經是資料裡最後一筆 label，就「更新」最後一筆數值
    （用最新抓到的價格取代，等於呈現「本月至今最新價」而非完整月均價）。
  - 若目前月份是新的一個月，就「新增」一筆。
  - 找不到 API 金鑰、或呼叫失敗時，會直接印出錯誤並以非 0 狀態碼結束，
    GitHub Actions 會在 Actions 分頁顯示失敗，但不會動到既有的 prices.json。
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.error
import csv
import io
import re

DATA_PATH = os.path.join(os.path.dirname(__file__), "prices.json")

EIA_API_KEY = os.environ.get("EIA_API_KEY", "").strip()
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
METALS_API_KEY = os.environ.get("METALS_API_KEY", "").strip()

BOT_CSV_URL = "https://rate.bot.com.tw/xrt/flcsv/0/day"
BOT_PAGE_URL = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
FX_CODES = ("USD", "CNY", "HKD", "EUR")


def http_get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "commodities-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def parse_bot_csv(raw):
    """Parse Bank of Taiwan's official daily CSV into spot bid/ask rates."""
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or "幣別" not in rows[0][0]:
        raise RuntimeError("臺銀匯率 CSV 格式不符或網站暫時阻擋")
    result = {}
    for row in rows[1:]:
        if len(row) < 5:
            continue
        match = re.search(r"\(([A-Z]{3})\)", row[0])
        if not match or match.group(1) not in FX_CODES:
            continue
        code = match.group(1)
        try:
            spot_buy, spot_sell = float(row[3]), float(row[4])
        except (TypeError, ValueError):
            continue
        if spot_buy <= 0 or spot_sell <= 0 or spot_buy > spot_sell:
            raise RuntimeError(f"臺銀 {code} 即期買賣價不合理")
        result[code] = {
            "spot_buy": spot_buy,
            "spot_sell": spot_sell,
            # 客戶拿新臺幣向銀行買外幣，採銀行即期賣出價。
            "twd_to_foreign": 1.0 / spot_sell,
        }
    missing = [code for code in FX_CODES if code not in result]
    if missing:
        raise RuntimeError("臺銀匯率缺少：" + ", ".join(missing))
    return result


def fetch_bot_rates(timeout=20):
    req = urllib.request.Request(
        BOT_CSV_URL,
        headers={
            "User-Agent": "Mozilla/5.0 TKP-commodity-tracker/2.0",
            "Accept": "text/csv,text/plain,*/*",
            "Referer": BOT_PAGE_URL,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return parse_bot_csv(raw)


def fetch_wti():
    """回傳最新一筆 WTI 現貨價 (USD/barrel)。
    先試 v2 的 facets 查詢法，失敗的話改用 v2 相容 v1 的 /seriesid/ 路徑。
    兩種都是 EIA 官方支援的查詢方式，寫兩種是為了提高穩定度。
    """
    if not EIA_API_KEY:
        raise RuntimeError("缺少 EIA_API_KEY，無法抓取原油價格")

    errors = []

    try:
        url = (
            "https://api.eia.gov/v2/petroleum/pri/spt/data/"
            f"?api_key={EIA_API_KEY}"
            "&frequency=daily"
            "&data[0]=value"
            "&facets[series][]=RWTC"
            "&sort[0][column]=period&sort[0][direction]=desc"
            "&offset=0&length=5"
        )
        payload = http_get_json(url)
        rows = payload.get("response", {}).get("data", [])
        if rows:
            latest = rows[0]
            return float(latest["value"]), latest["period"]
        errors.append(f"facets 查詢沒有資料：{payload}")
    except Exception as e:
        errors.append(f"facets 查詢失敗：{e}")

    try:
        url = f"https://api.eia.gov/v2/seriesid/PET.RWTC.D?api_key={EIA_API_KEY}"
        payload = http_get_json(url)
        rows = payload.get("response", {}).get("data", [])
        if rows:
            latest = rows[0]
            return float(latest["value"]), latest["period"]
        errors.append(f"/seriesid/ 查詢沒有資料：{payload}")
    except Exception as e:
        errors.append(f"/seriesid/ 查詢失敗：{e}")

    raise RuntimeError("；".join(errors))


def fetch_copper_fred():
    """回傳最新一筆 LME 銅價 (USD/公噸)，來源 FRED series PCOPPUSDM（IMF 官方資料）。
    這個 series 明確以 USD/Metric Ton 為單位，不需要猜測換算方式。
    月度資料，通常會有一兩個月的公告延遲，所以抓到的是「最新已公告」的月份，
    不一定是當月，這是官方資料本身的發布節奏，不是抓取邏輯的問題。
    """
    if not FRED_API_KEY:
        raise RuntimeError("缺少 FRED_API_KEY，無法抓取銅價")

    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=PCOPPUSDM&api_key={FRED_API_KEY}&file_type=json"
        "&sort_order=desc&limit=6"
    )
    payload = http_get_json(url)
    obs = payload.get("observations", [])
    for row in obs:
        val = row.get("value")
        if val and val != ".":  # FRED 用 "." 代表暫缺資料
            return float(val), row.get("date")
    raise RuntimeError(f"FRED 回傳沒有可用的銅價資料：{payload}")


def fetch_gold():
    """回傳最新一筆黃金現貨價 (USD/oz)，來源 MetalpriceAPI（免費方案支援貴金屬）。"""
    if not METALS_API_KEY:
        raise RuntimeError("缺少 METALS_API_KEY，無法抓取黃金價格")

    url = (
        "https://api.metalpriceapi.com/v1/latest"
        f"?api_key={METALS_API_KEY}"
        "&base=USD&currencies=XAU"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "commodities-tracker/1.0",
            "X-API-KEY": METALS_API_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if not payload.get("success", False):
        raise RuntimeError(f"MetalpriceAPI 回傳失敗：{payload}")

    rates = payload.get("rates", {})
    print(f"  MetalpriceAPI 原始回應 rates：{rates}")

    xau_raw = rates.get("XAU") or rates.get("USDXAU")
    if xau_raw is None:
        raise RuntimeError(f"回應中找不到黃金 (XAU)：{rates}")

    candidates = [xau_raw, (1.0 / xau_raw) if xau_raw else None]
    for val in candidates:
        if val is not None and 500 <= val <= 10000:
            return val
    raise RuntimeError(f"黃金價格換算結果不在合理範圍 (500~10000)，原始值：{xau_raw}")


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors = []
    oil_val = copper_val = gold_val = None
    fx_rates = None

    try:
        oil_val, oil_period = fetch_wti()
        print(f"WTI 最新價：{oil_val} USD/barrel（資料日期 {oil_period}）")
    except Exception as e:
        errors.append(f"原油抓取失敗：{e}")

    try:
        copper_val, copper_period = fetch_copper_fred()
        print(f"LME 銅最新價：{copper_val:.1f} USD/tonne（FRED 公告月份 {copper_period}）")
    except Exception as e:
        errors.append(f"銅價抓取失敗：{e}")

    try:
        gold_val = fetch_gold()
        print(f"黃金最新價：{gold_val:.2f} USD/oz")
    except Exception as e:
        errors.append(f"黃金抓取失敗：{e}")

    try:
        fx_rates = fetch_bot_rates()
        print("臺銀即期匯率：" + ", ".join(
            f"1 TWD = {fx_rates[code]['twd_to_foreign']:.6f} {code}" for code in FX_CODES
        ))
    except Exception as e:
        errors.append(f"臺銀匯率抓取失敗：{e}")

    if oil_val is None and copper_val is None and gold_val is None:
        print("三項資料全部抓取失敗，中止更新，保留原檔：")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    now = datetime.datetime.now(datetime.timezone.utc)
    current_label = now.strftime("%Y-%m")

    labels = data["labels"]

    data["previous_snapshot"] = {
        "oil": data["oil"][-1],
        "copper": data["copper"][-1],
        "gold": data["gold"][-1],
        "as_of": data.get("last_updated"),
    }

    if labels[-1] == current_label:
        if oil_val is not None:
            data["oil"][-1] = round(oil_val, 2)
        if copper_val is not None:
            data["copper"][-1] = round(copper_val, 1)
        if gold_val is not None:
            data["gold"][-1] = round(gold_val, 2)
    else:
        labels.append(current_label)
        data["oil"].append(round(oil_val, 2) if oil_val is not None else data["oil"][-1])
        data["copper"].append(round(copper_val, 1) if copper_val is not None else data["copper"][-1])
        data["gold"].append(round(gold_val, 2) if gold_val is not None else data["gold"][-1])

    data["last_updated"] = now.isoformat().replace("+00:00", "Z")

    meta = data.setdefault("meta", {})
    meta["oil"] = {
        "unit": "USD / barrel",
        "name": "WTI Crude Oil",
        "source": "U.S. EIA daily spot price (PET.RWTC.D)",
        "observation_date": oil_period if oil_val is not None else meta.get("oil", {}).get("observation_date"),
        "frequency": "daily",
    }
    meta["copper"] = {
        "unit": "USD / metric tonne",
        "name": "Copper monthly reference",
        "source": "FRED PCOPPUSDM / IMF monthly copper price",
        "source_url": "https://fred.stlouisfed.org/series/PCOPPUSDM",
        "observation_date": copper_period if copper_val is not None else meta.get("copper", {}).get("observation_date"),
        "frequency": "monthly_delayed",
        "warning": "不是 LME 當日 Cash Ask 或 3-month 報價",
    }
    meta["gold"] = {
        "unit": "USD / oz",
        "name": "Gold spot reference",
        "source": "MetalpriceAPI XAU spot reference",
        "observation_date": data["last_updated"] if gold_val is not None else meta.get("gold", {}).get("observation_date"),
        "frequency": "daily",
    }

    if fx_rates is not None:
        data["fx"] = {
            "base": "TWD",
            "basis": "1 TWD 可購買之外幣；依臺銀即期賣出價倒數計算",
            "source": "臺灣銀行牌告匯率",
            "source_url": BOT_PAGE_URL,
            "csv_url": BOT_CSV_URL,
            "fetched_at": data["last_updated"],
            "rates": fx_rates,
        }

    if errors:
        meta["last_run_warnings"] = errors
    elif "meta" in data and "last_run_warnings" in data["meta"]:
        del data["meta"]["last_run_warnings"]

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("已更新 prices.json")
    if errors:
        print("部分項目有警告（但仍保留可用資料）：")
        for e in errors:
            print(" -", e)


if __name__ == "__main__":
    main()
