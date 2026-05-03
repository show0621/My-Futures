import yfinance as yf
import pandas as pd
import numpy as np
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始下載市場資料並計算三層式量化模型...")
    df = yf.download("^TWII", period="730d", interval="1h")
    
    if df.empty:
        print("無法取得資料。")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)
    
    # -------------------------
    # 1. 基礎指標與共用參數
    # -------------------------
    df['SMA_100'] = df['Close'].rolling(window=100).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    valid_volume = df['Volume'] > df['Volume'].rolling(20).mean() * 0.5
    
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-5)
    
    # -------------------------
    # 2. 舊版基礎策略 (MACD)
    # -------------------------
    # 基礎波段
    df['Signal_Dir'] = 0
    df.loc[(df['Close'] > df['SMA_100']) & (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1)) & valid_volume, 'Signal_Dir'] = 1
    df.loc[(df['Close'] < df['SMA_100']) & (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1)) & valid_volume, 'Signal_Dir'] = -1
    df['Pos_Dir'] = np.floor(100 / df['ATR']).clip(lower=1, upper=3)
    df['Dir_Points'] = np.where(df['Signal_Dir'] == 1, df['Exit_Price'] - df['Entry_Price'], np.where(df['Signal_Dir'] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
    df['Dir_PnL_TWD'] = np.where(df['Signal_Dir'] != 0, (df['Dir_Points'] * 0.5 * 50 * df['Pos_Dir']) - (100 * df['Pos_Dir']), 0)

    # 基礎鐵蝴蝶
    df['Signal_IB'] = 0
    df.loc[(df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1) & valid_volume, 'Signal_IB'] = 1
    df['Pos_IB'] = df['Pos_Dir']
    ib_max_profit, ib_max_risk = 0.4 * df['ATR'], 0.6 * df['ATR']
    ib_points = np.where((ib_max_profit - np.abs(df['Exit_Price'] - df['Entry_Price'])) < -ib_max_risk, -ib_max_risk, ib_max_profit - np.abs(df['Exit_Price'] - df['Entry_Price']))
    df['IB_PnL_TWD'] = np.where(df['Signal_IB'] != 0, (ib_points * 50 * df['Pos_IB']) - (100 * df['Pos_IB']), 0)

    # -------------------------
    # 3. 法人三層式架構 (YZ波動率 + 動能)
    # -------------------------
    # 第一層：Yang-Zhang 波動率 (簡化版適用於Pandas)
    log_ho = np.log(df['High'] / df['Open'])
    log_lo = np.log(df['Low'] / df['Open'])
    log_co = np.log(df['Close'] / df['Open'])
    log_oc = np.log(df['Open'] / df['Close'].shift(1))
    rs_var = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    yz_var = log_oc.rolling(20).var() + 0.164 * log_co.rolling(20).var() + 0.836 * rs_var.rolling(20).mean()
    # 轉換為年化波動率 (60K 級別一年約 1260 根)
    df['YZ_Vol'] = np.sqrt(yz_var) * np.sqrt(1260)
    df['YZ_Vol'] = df['YZ_Vol'].replace(0, 0.01).fillna(0.15)

    # 第二層：多重時間動能 (20日, 60日, 120日 -> 換算為 100, 300, 600 根 60K)
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # 第三層：資金槓桿 (目標 30% 波動率)
    target_vol = 0.30
    df['Risk_Leverage'] = target_vol / df['YZ_Vol']

    # --- 三層式：買方多空策略 ---
    # 動能 > 0.3 作多，< -0.3 作空 (滿足你多空皆做的要求)
    df['Signal_3L_Dir'] = np.where(df['Composite_Score'] >= 0.33, 1, np.where(df['Composite_Score'] <= -0.33, -1, 0))
    # 最終口數 = 基礎2口 * 風險槓桿 * 動能強度，上限 5 口
    df['Pos_3L_Dir'] = np.floor(2 * df['Risk_Leverage'] * np.abs(df['Composite_Score'])).clip(0, 5)
    df['3L_Dir_Points'] = np.where(df['Signal_3L_Dir'] == 1, df['Exit_Price'] - df['Entry_Price'], np.where(df['Signal_3L_Dir'] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
    df['3L_Dir_PnL_TWD'] = np.where(df['Signal_3L_Dir'] != 0, (df['3L_Dir_Points'] * 0.5 * 50 * df['Pos_3L_Dir']) - (100 * df['Pos_3L_Dir']), 0)

    # --- 三層式：鐵蝴蝶中性策略 ---
    # 動能在 -0.3 到 0.3 之間 (盤整)，且 YZ 波動率小於均值時進場
    df['Signal_3L_IB'] = np.where((np.abs(df['Composite_Score']) < 0.33) & (df['YZ_Vol'] < df['YZ_Vol'].rolling(50).mean()), 1, 0)
    # 盤整時動能弱，口數主要受低波動率的槓桿放大
    df['Pos_3L_IB'] = np.floor(2 * df['Risk_Leverage'] * (1 - np.abs(df['Composite_Score']))).clip(0, 5)
    df['3L_IB_PnL_TWD'] = np.where(df['Signal_3L_IB'] != 0, (ib_points * 50 * df['Pos_3L_IB']) - (100 * df['Pos_3L_IB']), 0)

    # 儲存
    df.round(4).to_csv(FILE_PATH)
    print(f"資料更新完成，最新時間：{df.index[-1]}")

if __name__ == "__main__":
    fetch_and_process_data()
