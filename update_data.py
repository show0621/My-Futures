import yfinance as yf
import pandas as pd
import numpy as np
import os

# 資料存放路徑
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
FILE_PATH = os.path.join(DATA_DIR, "txf_options_backtest.csv")

def fetch_and_process_data():
    print("開始執行台指全方位策略回測計算 (含 5 年數據、風控 RM 邏輯)...")
    
    # 1. 抓取資料：設定為 5 年 (配合前端需求)
    # 使用 1h (60K) 資料進行回測
    df = yf.download("^TWII", period="5y", interval="1h")
    
    if df.empty:
        print("錯誤：無法從 yfinance 取得資料。")
        return

    # 處理多重索引問題 (yfinance 修正)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    
    df.dropna(inplace=True)

    # 2. 基礎技術指標計算
    df['SMA_100'] = df['Close'].rolling(100).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    
    # MACD 邏輯
    df['MACD'] = df['Close'].ewm(span=12).mean() - df['Close'].ewm(span=26).mean()
    df['Signal_Line'] = df['MACD'].ewm(span=9).mean()
    m_up = (df['MACD'] > df['Signal_Line']) & (df['MACD'].shift(1) <= df['Signal_Line'].shift(1))
    m_dn = (df['MACD'] < df['Signal_Line']) & (df['MACD'].shift(1) >= df['Signal_Line'].shift(1))
    
    # 3. 趨勢信心分數 (Composite_Score)：由 20, 60, 120 日趨勢組成
    # 60K 下，一天約 5 根 K 棒，故 100/300/600 約對應 20/60/120 日
    t1 = np.where(df['Close'] > df['Close'].shift(100), 1, -1)
    t2 = np.where(df['Close'] > df['Close'].shift(300), 1, -1)
    t3 = np.where(df['Close'] > df['Close'].shift(600), 1, -1)
    df['Composite_Score'] = (t1 + t2 + t3) / 3
    
    # 4. 波動率 (Yang-Zhang) 與 風險槓桿 (用於計算口數)
    log_co = np.log(df['Close'] / df['Open']).replace([np.inf, -np.inf], 0)
    df['YZ_Vol'] = (np.sqrt(log_co.rolling(20).var()) * np.sqrt(1260)).fillna(0.15)
    df['Risk_Leverage'] = (0.30 / df['YZ_Vol']).clip(0.5, 3.0)

    # 5. 出場時間點設定
    df['Entry_Price'] = df['Open'].shift(-1)  # 次根開盤進場
    df['Exit_Price_10d'] = df['Close'].shift(-50) # 原始 10 天持有 (50 根 60K)
    df['Exit_Price_7d'] = df['Close'].shift(-35)  # 風控 7 天持有 (35 根 60K)
    
    # 6. 生成各大大腦訊號 (Signal)
    # 法人 3L-Strict (0.33 門檻)
    df['Signal_3L_Strict'] = np.where(m_up & (df['Composite_Score'] >= 0.33), 1, 
                             np.where(m_dn & (df['Composite_Score'] <= -0.33), -1, 0))
    
    # 法人 3L-Relaxed (0 門檻)
    df['Signal_3L_Relaxed'] = np.where(m_up & (df['Composite_Score'] > 0), 1, 
                              np.where(m_dn & (df['Composite_Score'] < 0), -1, 0))
    
    # MAD 均線距離策略
    df['MAD_Value'] = (df['Close'] - df['SMA_20']) / df['SMA_20'] * 100
    df['Signal_MAD'] = 0
    df.loc[(df['MAD_Value'] > -1.5) & (df['MAD_Value'].shift(1) <= -1.5) & (df['Composite_Score'] > 0), 'Signal_MAD'] = 1
    df.loc[(df['MAD_Value'] < 1.5) & (df['MAD_Value'].shift(1) >= 1.5) & (df['Composite_Score'] < 0), 'Signal_MAD'] = -1
    
    # 基礎指標模型
    df['Signal_Dir'] = np.where(m_up & (df['Close'] > df['SMA_100']), 1, 
                       np.where(m_dn & (df['Close'] < df['SMA_100']), -1, 0))

    # 7. 統一執行損益計算 (包含各大大腦與 RM 風控組合)
    brain_list = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    
    for brain in brain_list:
        sig = f'Signal_{brain}'
        pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        df[f'Pos_{brain}'] = pos
        
        # 原始點數變動 (10 天)
        pts_10d = np.where(df[sig] == 1, df['Exit_Price_10d'] - df['Entry_Price'], 
                  np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        
        # --- ATR 動態停損停利與 7 天強制平倉邏輯 (RM 版本) ---
        raw_pts_7d = np.where(df[sig] == 1, df['Exit_Price_7d'] - df['Entry_Price'], 
                     np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        
        take_profit = df['ATR'] * 2.0
        stop_loss = df['ATR'] * 1.0
        
        # 模擬觸發停損停利後的點數
        pts_rm = np.where(raw_pts_7d >= take_profit, take_profit, 
                 np.where(raw_pts_7d <= -stop_loss, -stop_loss, raw_pts_7d))

        # --- A. 生成原始版欄位 (10 天) ---
        # 微台 (10元/點)
        df[f'{brain}_Micro_PnL_TWD'] = (pts_10d * 10 * pos) - (50 * pos)
        # 賣方收租 (期貨點數 + 100 點 Theta)
        df[f'{brain}_Seller_PnL_TWD'] = ((pts_10d + 100) * 10 * pos) - (100 * pos)
        # 純買方 (Delta 0.5, 扣除 500 點成本)
        df[f'{brain}_Buy_PnL_TWD'] = (pts_10d * 0.5 * 50 * pos) - (500 * pos)
        # 價差策略 (Delta 0.25, 扣除 200 點成本)
        df[f'{brain}_Spread_PnL_TWD'] = (pts_10d * 0.25 * 50 * pos) - (200 * pos)

        # --- B. 生成風控版欄位 (RM：7 天 + ATR) ---
        # 微台 RM
        df[f'{brain}_Micro_RM_PnL_TWD'] = (pts_rm * 10 * pos) - (50 * pos)
        # 賣方 RM (收租貼補降為 70 點)
        df[f'{brain}_Seller_RM_PnL_TWD'] = ((pts_rm + 70) * 10 * pos) - (100 * pos)
        # 純買方 RM (Theta 損耗降為 350)
        df[f'{brain}_Buy_RM_PnL_TWD'] = (pts_rm * 0.5 * 50 * pos) - (350 * pos)
        # 價差策略 RM (Theta 損耗降為 150)
        df[f'{brain}_Spread_RM_PnL_TWD'] = (pts_rm * 0.25 * 50 * pos) - (150 * pos)

    # 8. 鐵蝴蝶策略 (維持獨立)
    df['Signal_IB'] = 0
    df.loc[(df['ATR'] > df['ATR'].rolling(20).mean()) & (np.abs(df['MACD']) < df['ATR'] * 0.1), 'Signal_IB'] = 1
    df['Pos_IB'] = 2
    ib_pts = (0.4 * df['ATR'] - np.abs(df['Exit_Price_10d'] - df['Entry_Price'])).clip(lower=-0.6*df['ATR'])
    df['IB_PnL_TWD'] = (ib_pts * 50 * 2) - 200

    # 最終清理與存檔
    df.fillna(0).to_csv(FILE_PATH)
    print(f"成功更新 5 年期數據，檔案存於: {FILE_PATH}")

if __name__ == "__main__":
    fetch_and_process_data()
