# --- update_data.py 核心修改邏輯 ---

def fetch_and_process_data():
    # ... (前面的指標計算不變) ...

    # 定義出場點：原本 10 天 (50根) vs 7 天 (35根)
    df['Exit_Price_10d'] = df['Close'].shift(-50)
    df['Exit_Price_7d'] = df['Close'].shift(-35)

    for brain in brain_list:
        sig = f'Signal_{brain}'
        pos = np.floor(2 * df['Risk_Leverage']).clip(1, 5)
        
        # 取得進場後的價格矩陣 (未來 35 根 K 棒)，用於計算 ATR 動態停損停利
        # 註：這部分計算較重，建議僅針對有訊號的點計算
        
        raw_pts_10d = np.where(df[sig] == 1, df['Exit_Price_10d'] - df['Entry_Price'], 
                      np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))
        
        raw_pts_7d = np.where(df[sig] == 1, df['Exit_Price_7d'] - df['Entry_Price'], 
                     np.where(df[sig] == -1, df['Entry_Price'] - df['Exit_Price'], 0))

        # --- 新增：ATR 動態風控邏輯 (RM) ---
        # 簡單化模擬：若 7 天內最高點觸及 2*ATR 則以 2*ATR 計，若最低點觸及 1*ATR 則以 -1*ATR 計
        # 這裡生成標籤為 _RM 的欄位
        stop_loss = df['ATR'] * 1.0
        take_profit = df['ATR'] * 2.0
        
        # 假設 RM 策略下的點數 (以 7 天強制平倉為底)
        pts_rm = np.where(raw_pts_7d > take_profit, take_profit, 
                 np.where(raw_pts_7d < -stop_loss, -stop_loss, raw_pts_7d))

        # 寫入 CSV (供前端勾選)
        df[f'{brain}_Micro_PnL_TWD'] = (raw_pts_10d * 10 * pos) - (50 * pos)
        df[f'{brain}_Micro_RM_PnL_TWD'] = (pts_rm * 10 * pos) - (50 * pos) # 微台+風控
        
        # 買方與價差策略同理...
        df[f'{brain}_Buy_RM_PnL_TWD'] = (pts_rm * 0.5 * 50 * pos) - (350 * pos) # 7天 Theta 較少
