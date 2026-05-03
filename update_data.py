import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始執行多樣化策略回測（含微台與賣方收租）...")
    df = yf.download("^TWII", period="max", interval="1h")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 基礎指標
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 2. 趨勢與波動率 (YZ Vol)
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3
    
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    df['YZ_Vol'] = (np.sqrt(log_co.rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)

    # 3. 設定持有時間為 10 天 (50 根 60K K棒)
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-50)
    
    # 4. 產生訊號 (以 3L-Relaxed 為範例大腦)
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    df['Signal_Core'] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))

    # 5. 策略多樣化計算
    pts = np.where(df['Signal_Core'] == 1, df['Exit_Price'] - df['Entry_Price'], 
          np.where(df['Signal_Core'] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
    pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)

    # A. 純微台期策略 (每點 10 元，無時間價值損耗，手續費低)
    df['Micro_PnL_TWD'] = (pts * 10 * pos) - (50 * pos)

    # B. 買方多空策略 (每點 50 元，Delta 0.5，扣除 10 天 Theta)
    df['Buy_PnL_TWD'] = (pts * 0.5 * 50 * pos) - (500 * pos)

    # C. 台指期 + 賣方收租 (Covered Call/Put 概念)
    # 賺取期貨點數 (10元/微台) + 賣方時間價值貼補 (假設 10 天賺 100 點)
    df['Seller_PnL_TWD'] = ((pts + 100) * 10 * pos) - (100 * pos)

    # D. 價差策略 (Delta 0.25, 降低損耗)
    df['Spread_PnL_TWD'] = (pts * 0.25 * 50 * pos) - (200 * pos)

    # 填補空值並存檔
    for col in ['Micro_PnL_TWD', 'Buy_PnL_TWD', 'Seller_PnL_TWD', 'Spread_PnL_TWD']:
        df[col] = df[col].fillna(0)

    df.tail(3000).to_csv(FILE_PATH)
    print("多樣化策略回測成功")

if __name__ == "__main__":
    fetch_and_process_data()
