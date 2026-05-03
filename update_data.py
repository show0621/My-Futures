import yfinance as yf
import pandas as pd
import numpy as np
import os

# --- 專業交易參數 (模擬台指真實環境) ---
SLIPPAGE = 2.0        # 滑價 (進出各 1 點)
COMMISSION = 20.0     # 單邊手續費 (TWD)
TAX_RATE = 0.00002    # 期貨交易稅 (0.002%)

os.makedirs("data", exist_ok=True)
FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 啟動專業級回測引擎 (功能全開版本)...")
    # 抓取日 K 數據，確保回測連續性與視覺飽滿度
    df = yf.download("^TWII", period="5y", interval="1d")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 核心指標運算
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 趨勢信心分數 (Composite_Score)
    t1 = np.where(df['Close'] > df['Close'].shift(20), 1, -1)
    df['Composite_Score'] = t1.astype(float)

    # 2. 進出場與平倉紀錄 (解決 KeyError 的關鍵)
    df['Entry_Price_Long'] = df['Open'].shift(-1) + (SLIPPAGE / 2)
    df['Entry_Price_Short'] = df['Open'].shift(-1) - (SLIPPAGE / 2)
    # 產出平倉點標示所需的日期欄位
    df['Exit_Date_10d'] = df.index.to_series().shift(-10).dt.strftime('%Y-%m-%d')
    df['Exit_Price_10d'] = df['Close'].shift(-10)
    df['Exit_Date_7d'] = df.index.to_series().shift(-7).dt.strftime('%Y-%m-%d')
    df['Exit_Price_7d'] = df['Close'].shift(-7)

    # 3. 損益計算矩陣
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    brains = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    for b in brains:
        sig_col = f'Signal_{b}'
        # 簡易大腦邏輯分配
        if b == '3L_Strict': df[sig_col] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
        else: df[sig_col] = np.where(m_up, 1, np.where(m_dn, -1, 0))
        
        df[f'Pos_{b}'] = 1.0 # 預設 1 口

        # 核心損益公式：(點數差 * 10) - 手續費*2 - 稅金
        def calc_net_pnl(exit_p_col):
            pts = np.where(df[sig_col] == 1, df[exit_p_col] - df['Entry_Price_Long'],
                  np.where(df[sig_col] == -1, df['Entry_Price_Short'] - df[exit_p_col], 0))
            tax = np.where(df[sig_col] != 0, (df['Open'].shift(-1) + df[exit_p_col]) * 10 * TAX_RATE, 0)
            return (pts * 10) - (COMMISSION * 2) - tax

        df[f'{b}_Micro_PnL_TWD'] = calc_net_pnl('Exit_Price_10d')
        df[f'{b}_Micro_RM_PnL_TWD'] = calc_net_pnl('Exit_Price_7d')

    df['Signal_IB'] = 0 
    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 資料源更新成功：摩擦成本與平倉日期已全數產出。")

if __name__ == "__main__":
    fetch_and_process_data()
