import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始下載資料並執行多策略回測...")
    # 抓取極長資料以確保 120日(600根60K) 運算不會 NaN
    df = yf.download("^TWII", period="max", interval="1h")
    
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 基礎指標
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    exp1 = df['Close'].ewm(span=12).mean()
    exp2 = df['Close'].ewm(span=26).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    
    # 扳機：MACD 交叉
    macd_cross_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    macd_cross_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 2. 波動率與成交量濾網
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    valid_volume = df['Volume'] > df['Volume'].rolling(20).mean() * 0.5
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-5)

    # Yang-Zhang 波動率與槓桿
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    df['YZ_Vol'] = (np.sqrt(log_co.rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)

    # 3. 多重時間動能分數
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # --- 策略 A: 3L_Strict (0.33 門檻) ---
    df['Signal_3L_Strict'] = 0
    df.loc[macd_cross_up & (df['Composite_Score'] >= 0.33) & valid_volume, 'Signal_3L_Strict'] = 1
    df.loc[macd_cross_dn & (df['Composite_Score'] <= -0.33) & valid_volume, 'Signal_3L_Strict'] = -1

    # --- 策略 B: 3L_Relaxed (0 門檻) ---
    df['Signal_3L_Relaxed'] = 0
    df.loc[macd_cross_up & (df['Composite_Score'] > 0) & valid_volume, 'Signal_3L_Relaxed'] = 1
    df.loc[macd_cross_dn & (df['Composite_Score'] < 0) & valid_volume, 'Signal_3L_Relaxed'] = -1

    # --- 策略 C: MAD 移動均線距離策略 ---
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100
    df['Signal_MAD'] = 0
    # 實證邏輯：當價格在 100MA 之上，且 MAD 從負值回彈時買入 (超跌反彈)
    df.loc[(df['MAD_Value'] > -1) & (df['MAD_Value'].shift(1) <= -1) & (df['Close'] > df['SMA_100']), 'Signal_MAD'] = 1
    df.loc[(df['MAD_Value'] < 1) & (df['MAD_Value'].shift(1) >= 1) & (df['Close'] < df['SMA_100']), 'Signal_MAD'] = -1

    # 計算損益
    strategy_map = {
        '3L_Strict': 'Signal_3L_Strict',
        '3L_Relaxed': 'Signal_3L_Relaxed',
        'MAD': 'Signal_MAD'
    }
    
    for prefix, sig in strategy_map.items():
        df[f'Pos_{prefix}'] = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        pts = np.where(df[sig] == 1, df['Exit_Price'] - df['Entry_Price'], 
              np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        df[f'{prefix}_PnL'] = (pts * 0.5 * 50 * df[f'Pos_{prefix}']) - (100 * df[f'Pos_{prefix}'])
        df[f'{prefix}_PnL'] = df[f'{prefix}_PnL'].fillna(0)

    # 4. 鐵蝴蝶 (維持基礎版)
    df['Signal_IB'] = 0
    df.loc[(df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1), 'Signal_IB'] = 1
    df['Pos_IB'] = 2
    ib_pts = (0.4 * df['ATR'] - np.abs(df['Exit_Price'] - df['Entry_Price'])).clip(lower=-0.6*df['ATR'])
    df['IB_PnL_TWD'] = (ib_pts * 50 * 2) - 200

    df.tail(3000).to_csv(FILE_PATH)
    print("CSV 更新成功")

if __name__ == "__main__":
    fetch_and_process_data()
