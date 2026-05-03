import yfinance as yf
import pandas as pd
import numpy as np
import os

# 交易成本設定 (對齊專業審計精確度)
SLIPPAGE = 2.0        # 總滑價 (進出各 1 點)
COMMISSION = 20.0     # 單邊手續費
TAX_RATE = 0.00002    # 期貨交易稅 (0.002%)

os.makedirs("data", exist_ok=True)
FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 啟動日 K 級別專業回測引擎 (含摩擦成本計算)...")
    df = yf.download("^TWII", period="5y", interval="1d")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 核心指標運算
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 2. 進出場價格與平倉日期 (用於繪圖)
    df['Entry_Price_Long'] = df['Open'].shift(-1) + (SLIPPAGE / 2)
    df['Entry_Price_Short'] = df['Open'].shift(-1) - (SLIPPAGE / 2)
    df['Exit_Date_10d'] = df.index.to_series().shift(-10) # 記錄 10 天後的平倉日期
    df['Exit_Price_10d'] = df['Close'].shift(-10)

    # 3. 大腦訊號邏輯
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    df['Signal_3L_Strict'] = np.where(m_up, 1, np.where(m_dn, -1, 0))
    # ... 其他大腦邏輯可在此擴充 ...

    # 4. 淨損益計算 (扣除手續費與交易稅)
    for b in ['3L_Strict']:
        sig = f'Signal_{b}'
        # 點數盈虧 (扣除滑價)
        df[f'{b}_Gross_Pts'] = np.where(df[sig] == 1, df['Exit_Price_10d'] - df['Entry_Price_Long'],
                               np.where(df[sig] == -1, df['Entry_Price_Short'] - df['Exit_Price_10d'], 0))
        
        # 成本計算 (以微台 10元/點 為準)
        tax = np.where(df[sig] != 0, (df['Open'].shift(-1) + df['Close'].shift(-10)) * 10 * TAX_RATE, 0)
        comm = np.where(df[sig] != 0, COMMISSION * 2, 0)
        
        df[f'{b}_Micro_PnL_TWD'] = (df[f'{b}_Gross_Pts'] * 10) - tax - comm

    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 資料更新完成，包含摩擦成本與平倉紀錄。")

if __name__ == "__main__":
    fetch_and_process_data()
