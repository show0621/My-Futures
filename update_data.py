import yfinance as yf
import pandas as pd
import numpy as np
import os

# 設定儲存路徑
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始下載市場資料...")
    # 使用台灣加權指數 (^TWII) 作為台指的範例，時間級別設定為 60K (1h)
    # 實務上若要精確的 TXF 60K 與 TXO 報價，請在此替換為券商 API
    df = yf.download("^TWII", period="730d", interval="1h")
    
    if df.empty:
        print("無法取得資料，請檢查網路或 API。")
        return

    # 🔥 關鍵修復：攤平 yfinance 新版產生的雙層欄位索引 (MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df.dropna(inplace=True)
    
    # -------------------------
    # 1. 計算技術指標
    # -------------------------
    # 日線級別趨勢判斷：以 20 日均線為基準 (約略換算為 100 根 60K K棒)
    df['SMA_100'] = df['Close'].rolling(window=100).mean()
    
    # 60K 進出場依據：MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # 波動率計算：ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # -------------------------
    # 2. 策略邏輯與口數控管
    # -------------------------
    df['Signal'] = 0
    df['Position_Size'] = 0
    
    # 向量化運算買賣點
    # 做多 Call：價格在均線之上，且 MACD 黃金交叉
    condition_long = (df['Close'] > df['SMA_100']) & (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    # 買進 Put：價格在均線之下，且 MACD 死亡交叉
    condition_short = (df['Close'] < df['SMA_100']) & (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    df.loc[condition_long, 'Signal'] = 1
    df.loc[condition_short, 'Signal'] = -1
    
    # 波動率資金控管：設定目標風險點數為 100 點
    # 口數 = 預設風險 / 當前 ATR。波動越大，口數越小。
    target_risk_points = 100
    contracts = np.floor(target_risk_points / df['ATR'])
    contracts = contracts.clip(lower=1, upper=3) # 限制在 1 到 3 口之間
    
    # 只在有訊號的地方填入計算出的口數
    df.loc[df['Signal'] != 0, 'Position_Size'] = contracts.loc[df['Signal'] != 0]
    
    # -------------------------
    # 3. 模擬回測損益計算
    # -------------------------
    # 模擬進場後持有 5 根 K 棒 (5小時) 的點數變化 (實務上需替換為真實出場點邏輯)
    df['Forward_Return_Points'] = df['Close'].shift(-5) - df['Close']
    
    # 點數獲利計算：做多看漲，做空看跌
    df['Trade_Profit_Points'] = np.where(df['Signal'] == 1, df['Forward_Return_Points'], 
                                  np.where(df['Signal'] == -1, -df['Forward_Return_Points'], 0))
    
    # 轉換為選擇權損益 (以價平合約 Delta 約為 0.5 估算，台指選每點 50 元)
    # 扣除預估的買賣滑價與手續費 (假設每口成本 50 元)
    df['Options_Profit_TWD'] = (df['Trade_Profit_Points'] * 0.5 * 50 * df['Position_Size']) - (df['Position_Size'] * 50)
    df['Options_Profit_TWD'] = df['Options_Profit_TWD'].round(2)

    # -------------------------
    # 4. 儲存資料
    # -------------------------
    df.to_csv(FILE_PATH)
    print(f"資料已更新並儲存至 {FILE_PATH}，最新資料時間：{df.index[-1]}")

if __name__ == "__main__":
    fetch_and_process_data()
