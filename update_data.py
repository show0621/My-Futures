import yfinance as yf
import pandas as pd
import numpy as np
import os

# 確保路徑存在
os.makedirs("data", exist_ok=True)
FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 正在抓取 5 年期日 K 數據並執行量化運算...")
    # 改為日 K (1d)，確保 5 年數據完整且畫面辨識度高
    df = yf.download("^TWII", period="5y", interval="1d")
    
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 指標運算 (日 K 級別)
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 趨勢信心分數
    t1 = np.where(df['Close'] > df['Close'].shift(20), 1, -1) # 1個月
    t2 = np.where(df['Close'] > df['Close'].shift(60), 1, -1) # 1季
    t3 = np.where(df['Close'] > df['Close'].shift(120), 1, -1) # 半年
    df['Composite_Score'] = (t1 + t2 + t3) / 3
    
    # 風險與進出場
    df['YZ_Vol'] = (df['Close'].pct_change().rolling(20).std() * np.sqrt(252)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price_10d'] = df['Close'].shift(-10) # 10天
    df['Exit_Price_7d'] = df['Close'].shift(-7)   # 7天

    # 訊號與損益映射 (嚴格對齊前端組合名稱)
    brains = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    df['Signal_3L_Strict'] = np.where(m_up & (df['Composite_Score'] >= 0.33), 1, np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0))
    df['Signal_3L_Relaxed'] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
    df['Signal_MAD'] = np.where((df['Close'] < df['SMA_20']*0.985) & (df['Composite_Score']>0), 1, 0)
    df['Signal_Dir'] = np.where(m_up & (df['Close'] > df['SMA_100']), 1, np.where(m_dn & (df['Close'] < df['SMA_100']), -1, 0))

    for b in brains:
        sig = f'Signal_{b}'
        pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        df[f'Pos_{b}'] = pos
        pts_10 = np.where(df[sig]==1, df['Exit_Price_10d']-df['Entry_Price'], np.where(df[sig]==-1, df['Entry_Price']-df['Exit_Price'], 0))
        pts_7 = np.where(df[sig]==1, df['Exit_Price_7d']-df['Entry_Price'], np.where(df[sig]==-1, df['Entry_Price']-df['Exit_Price'], 0))
        pts_rm = np.where(pts_7 >= df['ATR']*2, df['ATR']*2, np.where(pts_7 <= -df['ATR'], -df['ATR'], pts_7))

        df[f'{b}_Micro_PnL_TWD'] = pts_10 * 10 * pos
        df[f'{b}_Micro_RM_PnL_TWD'] = pts_rm * 10 * pos
        df[f'{b}_Buy_PnL_TWD'] = pts_10 * 25 * pos - 500
        df[f'{b}_Buy_RM_PnL_TWD'] = pts_rm * 25 * pos - 350
        df[f'{b}_Seller_PnL_TWD'] = (pts_10 + 100) * 10 * pos
        df[f'{b}_Seller_RM_PnL_TWD'] = (pts_rm + 70) * 10 * pos
        df[f'{b}_Spread_PnL_TWD'] = pts_10 * 12.5 * pos - 200
        df[f'{b}_Spread_RM_PnL_TWD'] = pts_rm * 12.5 * pos - 150

    df['Signal_IB'] = 0
    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 日 K 級別回測數據更新完成。")

if __name__ == "__main__":
    fetch_and_process_data()
