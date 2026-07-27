# 原油・銅（LME）・黃金 五年價格追蹤 — 自動每日更新版

這個資料夾是一個完整的網站專案，放到 GitHub 上並照著下面步驟設定後，
會變成一個**每天自動更新一次**、任何人都能用網址打開的公開網頁。

網頁本身（`index.html`）不再把價格寫死在程式碼裡，而是每次打開時去讀
`data/prices.json`。另外有一個 GitHub Actions 排程（`.github/workflows/update-prices.yml`），
每天會自動執行 `scripts/update_prices.py`，去抓最新的原油、銅、黃金價格，
更新 `data/prices.json`，再自動 commit、push 回 repo；接著執行
`scripts/send_telegram.py`，把當天的價格摘要發到你設定好的 Telegram
（個人、群組、或頻道）。GitHub Pages 抓到新的 commit 後，網頁下次被
打開時就會顯示最新資料。

```
repo/
├── index.html                      ← 網頁本體
├── data/
│   └── prices.json                 ← 價格資料，每天被自動更新
├── scripts/
│   ├── update_prices.py            ← 抓資料、寫回 JSON 的程式
│   └── send_telegram.py            ← 把當天摘要發到 Telegram 的程式
└── .github/workflows/
    └── update-prices.yml           ← 每日排程設定
```

---

## 第一步：建立 GitHub 帳號與 repo

1. 如果還沒有帳號，先到 https://github.com 免費註冊。
2. 建立一個新的 repository（右上角「+」→「New repository」），名稱例如 `commodity-tracker`，
   設為 **Public**（GitHub Pages 免費方案需要 public repo），其餘用預設值即可。
3. 把這個資料夾裡的所有檔案（保留原本的資料夾結構）上傳到這個 repo。
   最簡單的方式是在 repo 頁面用「Add file → Upload files」把整包拖上去；
   如果你熟悉 git，也可以用 `git clone` 之後把檔案複製進去再 `git push`。

---

## 第二步：申請兩組免費 API 金鑰

### 1. EIA（美國能源資訊署）— 原油價格

- 前往 https://www.eia.gov/opendata/register.php 免費註冊，填 email 即可，
  註冊後金鑰會寄到信箱。
- 這是美國政府官方資料，完全免費、沒有每日次數限制的疑慮。

### 2. Metals-API — 銅（LME）與黃金價格

- 前往 https://metals-api.com 註冊免費帳號，登入後在 Dashboard 可以看到你的 `access_key`。
- 免費方案有每月呼叫次數上限（依方案而定，請以你登入後 Dashboard 顯示的實際額度為準）。
  本專案設計成**一天只呼叫一次**（把銅、黃金合併成一次 API 請求），
  一個月大約 30 次，一般免費額度都能負擔。
- 如果你申請後發現免費額度不夠用，或想改用其他資料源，替代方案包括
  `metalpriceapi.com`、`twelvedata.com` 等，只要在
  `scripts/update_prices.py` 的 `fetch_metals()` 裡把網址和欄位解析改成對應格式即可，
  程式裡都有註解說明。

> ⚠️ 目前免費 API 大多只提供「即時／近期現貨價」，不是每天完整的官方
> LME 官方結算價（那通常要付費訂閱 LME 官方資料）。這個方案抓到的是
> 「最接近的市場現貨價」，長期趨勢仍然有參考價值，但如果你需要交易等級的
> 精確報價，建議另外訂閱 LME 官方資料服務。

---

## 第三步：把金鑰加進 GitHub Secrets

1. 到你的 repo 頁面 → **Settings** → 左側選單 **Secrets and variables** → **Actions**。
2. 點 **New repository secret**，新增兩筆：
   - Name: `EIA_API_KEY`　　Value: 貼上你申請到的 EIA 金鑰
   - Name: `METALS_API_KEY`　Value: 貼上你申請到的 Metals-API 金鑰
3. 存檔即可，這些值不會顯示在程式碼或 log 裡。

---

## 第四步：開啟 GitHub Pages

1. repo 頁面 → **Settings** → 左側選單 **Pages**。
2. 「Source」選 **Deploy from a branch**，Branch 選 `main`，資料夾選 `/ (root)`，按 **Save**。
3. 等 1～2 分鐘，頁面上方會出現網址，類似：
   `https://你的帳號.github.io/commodity-tracker/`
   打開就能看到網頁（此時資料還是上傳時的舊資料，下一步讓它動起來）。

---

## 第五步：手動測試一次自動更新

1. repo 頁面 → **Actions** 分頁 → 左側選 **每日更新原物料價格**。
2. 右邊會有 **Run workflow** 按鈕，按下去手動觸發一次。
3. 等它跑完（通常 10～30 秒），綠勾勾代表成功。點進去可以看到
   log，會印出抓到的原油／銅／黃金最新價格。
4. 如果成功，`data/prices.json` 會多一個 commit，網頁重新整理後
   （記得清一下瀏覽器快取，或按 Ctrl+F5）就會看到新資料，
   頁面最下方也會顯示「資料最後更新」的時間。

之後它會照 `.github/workflows/update-prices.yml` 裡設定的時間
（預設 UTC 22:00，等於台北時間隔天早上 06:00）**每天自動跑一次**，
完全不需要你手動操作。想改時間的話，把 workflow 檔裡的
`cron: "0 22 * * *"` 改掉即可（前面數字依序是「分 時 日 月 星期」，都是 UTC 時間）。

---

## 第六步：設定 Telegram 每日通知

現在每天自動更新完資料後，還會多跑一步，把當天的原油／銅／黃金價格
整理成一則訊息，透過 Telegram 機器人發給你（也可以同時發到一個群組
或頻道，讓全公司同事都收得到）。

### 1. 建立 Telegram 機器人

1. 在 Telegram 搜尋並打開官方帳號 **@BotFather**。
2. 傳送 `/newbot`，照指示取個名字（顯示名稱）跟一個以 `bot` 結尾的
   使用者名稱（例如 `mycompany_commodity_bot`）。
3. 建立完成後，BotFather 會給你一串 **token**，長得像
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`，先複製起來，
   這就是等一下要填的 `TELEGRAM_BOT_TOKEN`。

### 2. 取得「發送對象」的 chat id

你可以同時發給多個對象（自己 + 同事的群組/頻道都行），
以下三種方式擇一或並用：

**A. 只發給你自己**
1. 在 Telegram 搜尋 **@userinfobot**，跟它對話一次，
   它會回你的個人 `chat id`（一串數字）。
2. 記得也要先去找你剛建立的機器人、跟它按一次「開始 / Start」，
   不然機器人沒辦法主動傳訊息給你。

**B. 發到一個群組（適合十幾人的小團隊）**
1. 建立一個 Telegram 群組，把同事都拉進來。
2. 把你的機器人也加進這個群組。
3. 在群組裡隨便傳一則訊息，然後在瀏覽器打開：
   `https://api.telegram.org/bot<你的TOKEN>/getUpdates`
   在回傳的 JSON 裡找 `"chat":{"id": -100xxxxxxxxxx, ...}`，
   那個負數就是群組的 chat id。

**C. 發到一個頻道（推薦！最適合「全公司都能看到」）**
1. 建立一個 Telegram **頻道**（Channel），例如取名「XX公司・原物料日報」。
2. 把機器人加進頻道，並設為**管理員**（至少要給「發送訊息」的權限）。
3. 同事只要拿到頻道的邀請連結加入，就能每天自動收到訊息，不需要
   機器人主動加好友，管理上最省事。
4. 如果頻道有設公開使用者名稱（例如 `@yourcompany_commodity`），
   直接把 `@yourcompany_commodity` 當作 chat id 使用即可；
   如果是私人頻道，一樣用上面 getUpdates 的方法，在頻道裡發一則訊息
   後去查詢，取得類似 `-100xxxxxxxxxx` 的數字 ID。

### 3. 把資訊加進 GitHub Secrets

回到 repo 的 **Settings → Secrets and variables → Actions**，新增：

- `TELEGRAM_BOT_TOKEN`　→ 貼上 BotFather 給的 token
- `TELEGRAM_CHAT_ID`　→ 貼上你要發送的對象。可以同時填多個，
  中間用逗號分開，例如：
  ```
  123456789,-1001234567890
  ```
  （上面例子代表同時發給「你自己」和「一個群組/頻道」）

### 4. 填上你的網頁網址

打開 `.github/workflows/update-prices.yml`，找到這一行：
```yaml
DASHBOARD_URL: "https://your-username.github.io/commodity-tracker/"
```
把它換成你在第四步拿到的實際 GitHub Pages 網址，存檔、commit。

### 5. 測試

到 **Actions** 分頁手動按一次 **Run workflow**。跑完之後，
你（跟群組/頻道裡的人）應該會馬上收到一則像這樣的訊息：

```
📊 原物料每日快報 — 2026-07-27（台北時間）

🛢️ 原油 WTI：$87.07 /桶 (📈 2.44%)
🟫 銅 LME：$12,934 /公噸 (📉 0.51%)
🟡 黃金 XAU：$4,053.75 /盎司 (📈 1.34%)

完整走勢圖：https://your-username.github.io/commodity-tracker/
```

之後每天排程跑的時候都會自動發送，不用再手動操作。

> 如果只是還沒設定 Telegram、暫時不想用這個功能，什麼都不用做——
> 沒有填 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 的話，
> 這個步驟會自動略過，不影響價格資料照常每天更新。

---

## 讓全公司同事都能看到：怎麼推廣這個儀表板

現在有兩個管道可以讓同事每天上班就看到最新的原物料指數動態，
建議兩個一起用：

1. **網頁**：GitHub Pages 的網址是公開的（例如
   `https://你的帳號.github.io/commodity-tracker/`），資料每天自動更新，
   把這個網址加進公司內部的常用書籤、內部 wiki 首頁、或瀏覽器啟動頁，
   同事一打開瀏覽器就能看到。因為只是公開市場的原物料價格，不含公司
   內部機密資訊，設成公開網址完全沒問題；如果你們有自己的網域，
   也可以把這個 GitHub Pages 綁定到公司子網域（例如
   `commodity.你們的公司.com`），GitHub Pages 的 Settings 裡有
   「Custom domain」欄位可以直接設定。

2. **Telegram 頻道**：照上面第六步「方式 C」建一個頻道，把同事都
   拉進去。這樣不需要大家記得每天主動打開網頁，機器人會每天早上
   主動推播一則簡短摘要（價格＋漲跌），有興趣看完整圖表的人
   再點訊息裡的連結進去看互動式走勢圖即可。



- **Actions 顯示失敗**：點進失敗的那次執行看 log，通常是金鑰打錯、或是
  API 免費額度用完。log 裡會印出明確的錯誤訊息。
- **Telegram 沒收到訊息**：最常見原因是還沒有先跟機器人按過「開始 / Start」
  （機器人沒辦法主動私訊沒對話過的人）、或是頻道裡機器人沒有「發送訊息」的
  管理員權限、或是 chat id 抄錯。可以直接在瀏覽器打開
  `https://api.telegram.org/bot<TOKEN>/getUpdates` 確認機器人有沒有收到過訊息、
  chat id 是不是你以為的那個。
- **Metals-API 回傳格式跟預期不同**：不同帳號方案有時候回傳的欄位結構會不一樣
  （例如金額是正的還是要取倒數）。`fetch_metals()` 裡已經寫了防呆判斷，
  如果還是不對，把 Actions log 裡印出的原始回應內容貼給我，我可以幫你調整。
- **本機測試 index.html**：因為網頁是用 `fetch()` 讀 `data/prices.json`，
  瀏覽器基於安全限制，直接雙擊打開檔案（`file://...`）通常會抓不到資料。
  想在本機測試，請在這個資料夾裡開終端機執行：
  ```
  python3 -m http.server 8000
  ```
  然後瀏覽器打開 `http://localhost:8000`。正式使用時放到 GitHub Pages 上就沒有這個問題。

---

## 之後想調整資料來源或畫面

- 想換一家 API：改 `scripts/update_prices.py` 就好，`index.html` 完全不用動，
  只要最後寫進 `data/prices.json` 的欄位格式（`labels` / `oil` / `copper` / `gold`
  都是等長的陣列）維持一樣即可。
- 想改網頁的文字、顏色、圖表：直接編輯 `index.html`，跟一般網頁一樣。
