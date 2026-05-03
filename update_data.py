import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始執行多樣化策略回測（持有 10 天波段）...")
    df = yf.download("^TWII", period="max", interval="1h")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 基礎指標
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 2. 趨勢與波動率
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3
    
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    df['YZ_Vol'] = (np.sqrt(log_co.rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)

    # 3. 持有時間設定：10 天 (50 根 60K)
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-50)
    
    # 4. 生成不同大腦的訊號 (Signal)
    df['Signal_3L_Strict'] = np.where(m_up & (df['Composite_Score'] >= 0.33), 1, np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0))
    df['Signal_3L_Relaxed'] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
    df['Signal_MAD'] = 0
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100
    df.loc[(df['MAD_Value'] > -1.5) & (df['MAD_Value'].shift(1) <= -1.5) & (df['Composite_Score'] > 0), 'Signal_MAD'] = 1
    df.loc[(df['MAD_Value'] < 1.5) & (df['MAD_Value'].shift(1) >= 1.5) & (df['Composite_Score'] < 0), 'Signal_MAD'] = -1
    df['Signal_Dir'] = np.where(m_up & (df['Close'] > df['SMA_100']), 1, np.where(m_dn & (df['Close'] < df['SMA_100']), -1, 0))

    # 5. 計算各類大腦對應的損益 (關鍵修復：命名規則)
    # 我們讓每個大腦都有自己的一組操作工具欄位
    brain_list = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    
    for brain in brain_list:
        sig = f'Signal_{brain}'
        pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        df[f'Pos_{brain}'] = pos
        pts = np.where(df[sig] == 1, df['Exit_Price'] - df['Entry_Price'], 
              np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))

        # A. 純買方 (Delta 0.5, 扣除 500 元 Theta)
        df[f'{brain}_Buy_PnL_TWD'] = (pts * 0.5 * 50 * pos) - (500 * pos)
        # B. 價差策略 (Delta 0.25, 扣除 200 元 Theta)
        df[f'{brain}_Spread_PnL_TWD'] = (pts * 0.25 * 50 * pos) - (200 * pos)
        # C. 微台期 (10元/點)
        df[f'{brain}_Micro_PnL_TWD'] = (pts * 10 * pos) - (50 * pos)
        # D. 賣方收租 (期貨 + 100 點時間價值)
        df[f'{brain}_Seller_PnL_TWD'] = ((pts + 100) * 10 * pos) - (100 * pos)

    # 6. 鐵蝴蝶策略 (維持獨立欄位)
    df['Signal_IB'] = 0
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df.loc[(df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1), 'Signal_IB'] = 1
    df['Pos_IB'] = 2
    ib_pts = (0.4 * df['ATR'] - np.abs(df['Exit_Price'] - df['Entry_Price'])).clip(lower=-0.6*df['ATR'])
    df['IB_PnL_TWD'] = (ib_pts * 50 * 2) - 200

    df.tail(3000).fillna(0).to_csv(FILE_PATH)
    print("CSV 更新成功，已生成所有複合欄位。")

if __name__ == "__main__":
    fetch_and_process_data()
