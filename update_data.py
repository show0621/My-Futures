import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("🚀 開始抓取數據...")
    df = yf.download("^TWII", period="5y", interval="1h")
    
    if df.empty:
        print("❌ 抓取失敗")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 指標運算
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 趨勢分數
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3
    
    # 進出場設定
    df['YZ_Vol'] = (np.sqrt(np.log(df['Close']/df['Open']).rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price_10d'] = df['Close'].shift(-50)
    df['Exit_Price_7d'] = df['Close'].shift(-35)

    # 大腦訊號
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    df['Signal_3L_Strict'] = np.where(m_up & (df['Composite_Score'] >= 0.33), 1, np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0))
    df['Signal_3L_Relaxed'] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100
    df['Signal_MAD'] = 0
    df.loc[(df['MAD_Value'] > -1.5) & (df['MAD_Value'].shift(1) <= -1.5) & (df['Composite_Score'] > 0), 'Signal_MAD'] = 1
    df.loc[(df['MAD_Value'] < 1.5) & (df['MAD_Value'].shift(1) >= 1.5) & (df['Composite_Score'] < 0), 'Signal_MAD'] = -1
    df['Signal_Dir'] = np.where(m_up & (df['Close'] > df['SMA_100']), 1, np.where(m_dn & (df['Close'] < df['SMA_100']), -1, 0))

    # 損益循環：嚴格對齊前綴
    for brain in ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']:
        sig = f'Signal_{brain}'
        pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        df[f'Pos_{brain}'] = pos
        
        pts_10 = np.where(df[sig] == 1, df['Exit_Price_10d'] - df['Entry_Price'], np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        pts_7 = np.where(df[sig] == 1, df['Exit_Price_7d'] - df['Entry_Price'], np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        
        # RM 風控
        tp, sl = df['ATR'] * 2.0, df['ATR'] * 1.0
        pts_rm = np.where(pts_7 >= tp, tp, np.where(pts_7 <= -sl, -sl, pts_7))

        # 寫入各欄位 (確保名稱與 app.py 的映射完全一致)
        df[f'{brain}_Micro_PnL_TWD'] = (pts_10 * 10 * pos) - (50 * pos)
        df[f'{brain}_Micro_RM_PnL_TWD'] = (pts_rm * 10 * pos) - (50 * pos)
        df[f'{brain}_Buy_PnL_TWD'] = (pts_10 * 0.5 * 50 * pos) - (500 * pos)
        df[f'{brain}_Buy_RM_PnL_TWD'] = (pts_rm * 0.5 * 50 * pos) - (350 * pos)
        df[f'{brain}_Seller_PnL_TWD'] = ((pts_10 + 100) * 10 * pos) - (100 * pos)
        df[f'{brain}_Seller_RM_PnL_TWD'] = ((pts_rm + 70) * 10 * pos) - (100 * pos)
        df[f'{brain}_Spread_PnL_TWD'] = (pts_10 * 0.25 * 50 * pos) - (200 * pos)
        df[f'{brain}_Spread_RM_PnL_TWD'] = (pts_rm * 0.25 * 50 * pos) - (150 * pos)

    df.fillna(0).to_csv(FILE_PATH)
    print("✅ CSV 更新成功！目前包含欄位：")
    print(df.columns.tolist())

if __name__ == "__main__":
    fetch_and_process_data()
