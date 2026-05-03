import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    # 抓取長天期資料確保 120日(600根60K) 運算不為 NaN
    df = yf.download("^TWII", period="max", interval="1h")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 指標計算
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 進場扳機
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 趨勢信心分數 (20, 60, 120日)
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # MAD 距離計算
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100

    # 執行三種不同門檻的策略計算
    for prefix, sig in [('3L_Strict', 0.33), ('3L_Relaxed', 0), ('MAD', 0)]:
        if prefix == 'MAD':
            df['Signal_MAD'] = np.where((df['MAD_Value'] > -1) & (df['MAD_Value'].shift(1) <= -1) & (df['Close'] > df['SMA_100']), 1, 
                               np.where((df['MAD_Value'] < 1) & (df['MAD_Value'].shift(1) >= 1) & (df['Close'] < df['SMA_100']), -1, 0))
        else:
            df[f'Signal_{prefix}'] = np.where(m_up & (df['Composite_Score'] >= sig), 1, 
                                     np.where(m_dn & (df['Composite_Score'] <= -sig), -1, 0))

    # 儲存與輸出
    df.tail(3000).to_csv(FILE_PATH)
    print("回測數據已更新")

if __name__ == "__main__":
    fetch_and_process_data()
