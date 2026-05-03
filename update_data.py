import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始執行台指期日K追蹤與多策略回測...")
    # 抓取長天期資料確保 120日(約600根60K) 運算不為 NaN
    df = yf.download("^TWII", period="max", interval="1h")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 基礎指標計算
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 扳機：MACD 交叉
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 2. 趨勢信心分數 (20, 60, 120日)
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # 3. 波動率與進出場設定
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    df['YZ_Vol'] = (np.sqrt(log_co.rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-5)

    # 4. MAD 均線距離策略 (多空雙向)
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100
    df['Signal_MAD'] = 0
    # 做多：長線多頭且低點回彈；做空：長線空頭且高點回跌
    df.loc[(df['MAD_Value'] > -1.5) & (df['MAD_Value'].shift(1) <= -1.5) & (df['Composite_Score'] > 0), 'Signal_MAD'] = 1
    df.loc[(df['MAD_Value'] < 1.5) & (df['MAD_Value'].shift(1) >= 1.5) & (df['Composite_Score'] < 0), 'Signal_MAD'] = -1

    # 5. 法人策略訊號
    df['Signal_3L_Strict'] = np.where(m_up & (df['Composite_Score'] >= 0.33), 1, np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0))
    df['Signal_3L_Relaxed'] = np.where(m_up & (df['Composite_Score'] > 0), 1, np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
    df['Signal_Dir'] = np.where(m_up & (df['Close'] > df['SMA_100']), 1, np.where(m_dn & (df['Close'] < df['SMA_100']), -1, 0))

    # 6. 損益計算核心
    strat_list = [
        ('3L_Strict', 'Signal_3L_Strict'),
        ('3L_Relaxed', 'Signal_3L_Relaxed'),
        ('MAD', 'Signal_MAD'),
        ('Dir', 'Signal_Dir')
    ]
    
    for name, sig_col in strat_list:
        df[f'Pos_{name}'] = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        points = np.where(df[sig_col] == 1, df['Exit_Price'] - df['Entry_Price'], 
                 np.where(df[sig_col] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        # 損益欄位名稱必須與前端對接
        df[f'{name}_PnL_TWD'] = (points * 0.5 * 50 * df[f'Pos_{name}']) - (100 * df[f'Pos_{name}'])
        df[f'{name}_PnL_TWD'] = df[f'{name}_PnL_TWD'].fillna(0)

    # 7. 鐵蝴蝶策略
    df['Signal_IB'] = 0
    df.loc[(df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1), 'Signal_IB'] = 1
    df['Pos_IB'] = 2
    ib_pts = (0.4 * df['ATR'] - np.abs(df['Exit_Price'] - df['Entry_Price'])).clip(lower=-0.6*df['ATR'])
    df['IB_PnL_TWD'] = (ib_pts * 50 * 2) - 200

    df.tail(3000).to_csv(FILE_PATH)
    print("回測數據已更新")

if __name__ == "__main__":
    fetch_and_process_data()
