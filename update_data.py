import yfinance as yf
import pandas as pd
import numpy as np
import os

# --- 專業審計級參數設定 ---
SLIPPAGE = 2.0        # 總滑價 (進出各 1 點)
COMMISSION = 20.0     # 單邊手續費 (TWD)
TAX_RATE = 0.00002    # 期貨交易稅 (0.002%)

os.makedirs("data", exist_ok=True)
FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 啟動日 K 級別專業回測引擎 (含摩擦成本計算)...")
    df = yf.download("^TWII", period="5y", interval="1d")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 指標運算
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 2. 趨勢信心分數 (Composite_Score)
    t1 = np.where(df['Close'] > df['Close'].shift(20), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(60), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(120), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # 3. 進出場與平倉紀錄
    df['Entry_Price_Long'] = df['Open'].shift(-1) + (SLIPPAGE / 2)
    df['Entry_Price_Short'] = df['Open'].shift(-1) - (SLIPPAGE / 2)
    df['Exit_Date_10d'] = df.index.to_series().shift(-10) 
    df['Exit_Price_10d'] = df['Close'].shift(-10)
    df['Exit_Price_7d'] = df['Close'].shift(-7)

    # 4. 生成大腦訊號
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    brains = {
        '3L_Strict': np.where(m_up & (df['Composite_Score'] >= 0.33), 1, np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0)),
        '3L_Relaxed': np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0)),
        'MAD': np.where((df['Close'] < df['SMA_20']*0.985) & (df['Composite_Score'] > 0), 1, 0),
        'Dir': np.where(m_up, 1, np.where(m_dn, -1, 0))
    }

    for b, sig_data in brains.items():
        sig_col = f'Signal_{b}'
        df[sig_col] = sig_data
        pos = 1.0 
        df[f'Pos_{b}'] = pos
        
        # 損益計算 (10天與7天)
        def calc_pnl(exit_p_col, is_rm=False):
            pts = np.where(df[sig_col] == 1, df[exit_p_col] - df['Entry_Price_Long'],
                  np.where(df[sig_col] == -1, df['Entry_Price_Short'] - df[exit_p_col], 0))
            
            # 成本模型：滑價已含在 Entry/Exit Price 中，此處扣除稅與手續費
            tax = np.where(df[sig_col] != 0, (df['Open'].shift(-1) + df[exit_p_col]) * 10 * TAX_RATE, 0)
            comm = np.where(df[sig_col] != 0, COMMISSION * 2, 0)
            return (pts * 10) - tax - comm

        df[f'{b}_Micro_PnL_TWD'] = calc_pnl('Exit_Price_10d')
        df[f'{b}_Micro_RM_PnL_TWD'] = calc_pnl('Exit_Price_7d', is_rm=True)

    df['Signal_IB'] = 0 
    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 後端數據更新完成 (含摩擦成本與 RM 欄位)。")

if __name__ == "__main__":
    fetch_and_process_data()
