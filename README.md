# 台指期貨波段監控（30分K / 60分K / 日K）

這是一個可直接啟動的 Web 範例：

- 即時（輪詢）產出多空訊號
- 規則：7 天強制平倉、10% 停損、動態追蹤停利
- 同步進行虛擬交易（paper trading）
- 每個週期都能看回測摘要

> 預設用 `^TWII` 當資料來源示範。你可以在 `DataProvider(symbol="^TWII")` 改成你可用的台指期商品代碼或券商 API。

## 1) 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) 啟動

```bash
uvicorn app.main:app --reload --port 8000
```

打開 `http://127.0.0.1:8000`。

## 策略邏輯（動能趨勢）

- 指標：EMA12、EMA34、10 根動能、RSI(14)
- 做多：EMA12 > EMA34 且動能 > 0 且 RSI > 55
- 做空：EMA12 < EMA34 且動能 < 0 且 RSI < 45
- 出場：
  - 持倉 >= 7 天：強制平倉
  - 停損 10%
  - 追蹤停利（預設 4% 回吐）
  - 反向訊號反手

## API

- `GET /api/signal`：讀取最新訊號
- `POST /api/refresh`：強制重新抓資料並刷新

## 後續可擴充

1. 串台灣期交所授權資料源 / 券商 API（如 Shioaji）
2. 把交易成本（手續費/滑價）納入回測
3. 用 WebSocket 推播代替輪詢
4. 增加策略參數最佳化頁面
# 台指期貨波段監控（30分K / 60分K / 日K）

這個專案現在提供兩種介面：

1. FastAPI + HTML Dashboard
2. Streamlit Dashboard（可直接部署到 Streamlit Community Cloud）

功能包含：

- 手動刷新產出多空訊號（Streamlit 版）
- 即時（輪詢）產出多空訊號（FastAPI 版）
- 規則：7 天強制平倉、10% 停損、動態追蹤停利
- 同步進行虛擬交易（paper trading）
- 每個週期都能看回測摘要

> 預設用 `^TWII` 當資料來源示範。你可以在 `SignalService(symbol="^TWII")` 改成你可用的台指期商品代碼或券商 API。

## 1) 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) 啟動 FastAPI 版

```bash
uvicorn app.main:app --reload --port 8000
```

打開 `http://127.0.0.1:8000`。

## 3) 啟動 Streamlit 版

```bash
streamlit run streamlit_app.py
```

## Streamlit Cloud 發佈步驟（不會動到你原本 Streamlit 其他資料）

1. 將本專案 push 到一個新的 Git repo（或新的 branch）。
2. 到 Streamlit Community Cloud 新增 App。
3. Repository 指向此專案。
4. Main file path 設成：`streamlit_app.py`。
5. 讓平台自動用 `requirements.txt` 安裝依賴。

> 這次實作是新增 `streamlit_app.py`，沒有去改你原本既有的 Streamlit 檔案與資料。

## 策略邏輯（動能趨勢）

- 指標：EMA12、EMA34、10 根動能、RSI(14)
- 做多：EMA12 > EMA34 且動能 > 0 且 RSI > 55
- 做空：EMA12 < EMA34 且動能 < 0 且 RSI < 45
- 出場：
  - 持倉 >= 7 天：強制平倉
  - 停損 10%
  - 追蹤停利（預設 4% 回吐）
  - 反向訊號反手

## API

- `GET /api/signal`：讀取最新訊號
- `POST /api/refresh`：強制重新抓資料並刷新

## 後續可擴充

1. 串台灣期交所授權資料源 / 券商 API（如 Shioaji）
2. 把交易成本（手續費/滑價）納入回測
3. 用 WebSocket 推播代替輪詢
4. 增加策略參數最佳化頁面

## Streamlit 沒有產出時先檢查

1. 進入 Streamlit Cloud 的 App `Manage app` -> `Logs` 看錯誤訊息。
2. 確認 Main file path 是 `streamlit_app.py`。
3. 確認 Python version 使用 3.10+。
4. 若外部行情抓不到，本專案會自動 fallback mock 資料，不會整頁空白；若仍空白，通常是安裝或路徑設定問題。
