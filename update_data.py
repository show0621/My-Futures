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
    
    # 🔥 定義精準進場扳機 (Trigger)：MACD 交叉
    macd_cross_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    macd_cross_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    valid_volume = df['Volume'] > df['Volume'].rolling(20).mean() * 0.5
    
    df['Entry_Price'] = df['Open'].shift(-1)
    df['Exit_Price'] = df['Close'].shift(-5)
    
    # -------------------------
    # 2. 舊版基礎策略 (單純依賴 MACD)
    # -------------------------
    df['Signal_Dir'] = 0
    df.loc[(df['Close'] > df['SMA_100']) & macd_cross_up & valid_volume, 'Signal_Dir'] = 1
    df.loc[(df['Close'] < df['SMA_100']) & macd_cross_dn & valid_volume, 'Signal_Dir'] = -1
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
    # 3. 法人三層式架構 (YZ波動率 + 動能濾網 + 交叉扳機)
    # -------------------------
    # 第一層：Yang-Zhang 波動率
    log_ho = np.log(df['High'] / df['Open']).replace([np.inf, -np.inf], 0)
    log_lo = np.log(df['Low'] / df['Open']).replace([np.inf, -np.inf], 0)
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    log_oc = np.log(df['Open'] / df['Close'].shift(1)).replace([np.inf, -np.inf], 0)
    rs_var = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    yz_var = log_oc.rolling(20).var() + 0.164 * log_co.rolling(20).var() + 0.836 * rs_var.rolling(20).mean()
    df['YZ_Vol'] = np.sqrt(yz_var) * np.sqrt(1260)
    # 🔥 防呆：用前值填補 NaN，若還是空值則預設 15% 波動率
    df['YZ_Vol'] = df['YZ_Vol'].replace([np.inf, -np.inf, 0], np.nan).fillna(method='bfill').fillna(0.15)

    # 第二層：多重時間動能濾網 (換算為 100, 300, 600 根 60K)
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3

    # 第三層：資金槓桿 (目標 30% 波動率)
    target_vol = 0.30
    df['Risk_Leverage'] = (target_vol / df['YZ_Vol']).replace([np.inf, -np.inf], 1).fillna(1)

    # --- 三層式：買方多空策略 (修復過度交易) ---
    df['Signal_3L_Dir'] = 0
    # 🔥 關鍵修復：必須同時滿足「MACD 剛交叉 (扳機)」且「趨勢分數吻合 (濾網)」才進場
    df.loc[macd_cross_up & (df['Composite_Score'] >= 0.33) & valid_volume, 'Signal_3L_Dir'] = 1
    df.loc[macd_cross_dn & (df['Composite_Score'] <= -0.33) & valid_volume, 'Signal_3L_Dir'] = -1
    
    df['Pos_3L_Dir'] = np.floor(2 * df['Risk_Leverage'] * np.abs(df['Composite_Score'])).clip(0, 5)
    df['3L_Dir_Points'] = np.where(df['Signal_3L_Dir'] == 1, df['Exit_Price'] - df['Entry_Price'], np.where(df['Signal_3L_Dir'] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
    df['3L_Dir_PnL_TWD'] = np.where(df['Signal_3L_Dir'] != 0, (df['3L_Dir_Points'] * 0.5 * 50 * df['Pos_3L_Dir']) - (100 * df['Pos_3L_Dir']), 0)
    df['3L_Dir_PnL_TWD'] = df['3L_Dir_PnL_TWD'].fillna(0) # 確保絕對不會出現 NaN

    # --- 三層式：鐵蝴蝶中性策略 ---
    df['Signal_3L_IB'] = 0
    ib_trigger = (df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1) & valid_volume
    df.loc[ib_trigger & (df['Composite_Score'].abs() < 0.33) & (df['YZ_Vol'] < df['YZ_Vol'].rolling(50).mean()), 'Signal_3L_IB'] = 1
    
    df['Pos_3L_IB'] = np.floor(2 * df['Risk_Leverage'] * (1 - np.abs(df['Composite_Score']))).clip(0, 5)
    df['3L_IB_PnL_TWD'] = np.where(df['Signal_3L_IB'] != 0, (ib_points * 50 * df['Pos_3L_IB']) - (100 * df['Pos_3L_IB']), 0)
    df['3L_IB_PnL_TWD'] = df['3L_IB_PnL_TWD'].fillna(0) # 確保絕對不會出現 NaN

    # 把前 100 根用來算均線導致數據不全的殘廢 K 棒剃除，讓圖表更乾淨
    df.dropna(subset=['SMA_100'], inplace=True)

    # 儲存
    df.round(4).to_csv(FILE_PATH)
    print(f"資料更新完成，最新時間：{df.index[-1]}")

if __name__ == "__main__":
    fetch_and_process_data()
