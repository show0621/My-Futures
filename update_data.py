import yfinance as yf
import pandas as pd
import numpy as np
import os

# --- 專業交易參數 ---
SLIPPAGE = 2.0        # 滑價 (進出各 1 點)
COMMISSION = 20.0     # 單邊手續費 (TWD)
TAX_RATE = 0.00002    # 期貨交易稅 (0.002%)

os.makedirs("data", exist_ok=True)
FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 啟動專業級回測引擎更新...")
    df = yf.download("^TWII", period="5y", interval="1d")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 核心指標與趨勢分數
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    t1 = np.where(df['Close'] > df['Close'].shift(20), 1, -1)
    df['Composite_Score'] = t1 # 簡化邏輯確保穩定

    # 2. 進出場價格與平倉紀錄 (KeyError 修復點)
    df['Entry_Price_Long'] = df['Open'].shift(-1) + (SLIPPAGE / 2)
    df['Entry_Price_Short'] = df['Open'].shift(-1) - (SLIPPAGE / 2)
    # 產出 app.py 報錯缺失的欄位
    df['Exit_Date_10d'] = df.index.to_series().shift(-10).dt.strftime('%Y-%m-%d')
    df['Exit_Price_10d'] = df['Close'].shift(-10)

    # 3. 訊號生成 (以 3L_Strict 為例)
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 映射各策略大腦
    brains = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    for b in brains:
        sig_col = f'Signal_{b}'
        df[sig_col] = np.where(m_up, 1, np.where(m_dn, -1, 0))
        
        # 淨損益計算 (扣除摩擦成本)
        pts = np.where(df[sig_col] == 1, df['Exit_Price_10d'] - df['Entry_Price_Long'],
              np.where(df[sig_col] == -1, df['Entry_Price_Short'] - df['Exit_Price_10d'], 0))
        
        tax = np.where(df[sig_col] != 0, (df['Open'].shift(-1) + df['Close'].shift(-10)) * 10 * TAX_RATE, 0)
        df[f'{b}_Micro_PnL_TWD'] = (pts * 10) - (COMMISSION * 2) - tax
        df[f'Pos_{b}'] = 1.0

    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 資料更新完成。")

if __name__ == "__main__":
    fetch_and_process_data()
