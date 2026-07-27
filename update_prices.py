#!/usr/bin/env python3
"""
每日更新 data/prices.json：
  - 原油 WTI：美國 EIA 官方 API（series PET.RWTC.D，每日現貨價）
  - 銅：LME 銅（LME-XCU）settlement price，經 Metals-API 取得，單位 USD/tonne
  - 黃金：XAU 現貨價，經 Metals-API 取得，單位 USD/oz

需要的環境變數（由 GitHub Actions secrets 注入）：
  EIA_API_KEY      - 到 https://www.eia.gov/opendata/register.php 免費申請
  METALS_API_KEY   - 到 https://metals-api.com （或替代服務，見下方 FALLBACK 註解）申請

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

DATA_PATH = os.path.join(os.path.dirname(__file__), "prices.json")son")

EIA_API_KEY = os.environ.get("EIA_API_KEY", "").strip()
METALS_API_KEY = os.environ.get("METALS_API_KEY", "").strip()


def http_get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "commodities-tracker/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def fetch_wti():
    """回傳最新一筆 WTI 現貨價 (USD/barrel)。
    先試 v2 的 facets 查詢法，失敗的話改用 v2 相容 v1 的 /seriesid/ 路徑。
    兩種都是 EIA 官方支援的查詢方式，寫兩種是為了提高穩定度。
    """
    if not EIA_API_KEY:
        raise RuntimeError("缺少 EIA_API_KEY，無法抓取原油價格")

    errors = []

    # 方法一：v2 facets 查詢
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

    # 方法二（備援）：v2 相容 v1 的 /seriesid/ 路徑
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


def fetch_metals():
    """回傳 (copper_usd_per_tonne, gold_usd_per_oz)，來源 Metals-API。"""
    if not METALS_API_KEY:
        raise RuntimeError("缺少 METALS_API_KEY，無法抓取銅／黃金價格")

    url = (
        "https://metals-api.com/api/latest"
        f"?access_key={METALS_API_KEY}"
        "&base=USD&symbols=XAU,LME-XCU"
    )
    payload = http_get_json(url)
    if not payload.get("success", False):
        raise RuntimeError(f"Metals-API 回傳失敗：{payload}")

    rates = payload["rates"]

    # --- 黃金 XAU ---
    # Metals-API 對貴金屬通常回傳「1 USD = 多少盎司黃金」的反向匯率，
    # 所以真正的美元/盎司價格 = 1 / rates['XAU']。
    # 但不同帳戶/方案偶爾格式不同，這裡做防呆判斷：
    xau_raw = rates.get("XAU")
    if xau_raw is None:
        raise RuntimeError(f"回應中找不到 XAU：{rates}")
    gold_usd_per_oz = (1.0 / xau_raw) if xau_raw < 1 else xau_raw

    # --- 銅 LME-XCU ---
    xcu_raw = rates.get("LME-XCU")
    if xcu_raw is None:
        raise RuntimeError(f"回應中找不到 LME-XCU：{rates}")
    # LME-XCU 若是「每美元可換多少單位」的反向匯率（數值遠小於 1），要取倒數；
    # 若已經是每噸價格（數值落在幾千到幾萬區間），就直接使用。
    if xcu_raw < 1:
        copper_usd_per_tonne = 1.0 / xcu_raw
    else:
        copper_usd_per_tonne = xcu_raw

    return copper_usd_per_tonne, gold_usd_per_oz


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors = []
    oil_val = copper_val = gold_val = None

    try:
        oil_val, oil_period = fetch_wti()
        print(f"WTI 最新價：{oil_val} USD/barrel（資料日期 {oil_period}）")
    except Exception as e:
        errors.append(f"原油抓取失敗：{e}")

    try:
        copper_val, gold_val = fetch_metals()
        print(f"LME 銅最新價：{copper_val:.1f} USD/tonne")
        print(f"黃金最新價：{gold_val:.2f} USD/oz")
    except Exception as e:
        errors.append(f"銅／黃金抓取失敗：{e}")

    if oil_val is None and copper_val is None and gold_val is None:
        print("三項資料全部抓取失敗，中止更新，保留原檔：")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    now = datetime.datetime.now(datetime.timezone.utc)
    current_label = now.strftime("%Y-%m")

    labels = data["labels"]

    # 記錄「這次更新之前」的數值，讓通知腳本可以算出「較上次」的漲跌幅
    data["previous_snapshot"] = {
        "oil": data["oil"][-1],
        "copper": data["copper"][-1],
        "gold": data["gold"][-1],
        "as_of": data.get("last_updated"),
    }

    if labels[-1] == current_label:
        # 同一個月份 -> 更新最後一筆
        if oil_val is not None:
            data["oil"][-1] = round(oil_val, 2)
        if copper_val is not None:
            data["copper"][-1] = round(copper_val, 1)
        if gold_val is not None:
            data["gold"][-1] = round(gold_val, 2)
    else:
        # 新的月份 -> 新增一筆（缺漏的項目就沿用上個月數值，避免圖表斷裂）
        labels.append(current_label)
        data["oil"].append(round(oil_val, 2) if oil_val is not None else data["oil"][-1])
        data["copper"].append(round(copper_val, 1) if copper_val is not None else data["copper"][-1])
        data["gold"].append(round(gold_val, 2) if gold_val is not None else data["gold"][-1])

    data["last_updated"] = now.isoformat().replace("+00:00", "Z")

    if errors:
        data.setdefault("meta", {})["last_run_warnings"] = errors
    elif "meta" in data and "last_run_warnings" in data["meta"]:
        del data["meta"]["last_run_warnings"]

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("已更新 data/prices.json")
    if errors:
        print("部分項目有警告（但仍保留可用資料）：")
        for e in errors:
            print(" -", e)


if __name__ == "__main__":
    main()
