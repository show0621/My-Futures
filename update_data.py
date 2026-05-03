import yfinance as yf
import pandas as pd
import numpy as np
import os

# 交易參數設定 (依台股現制)
SLIPPAGE = 2.0        # 滑價預設 2 點 (單邊 1 點)
COMMISSION = 20.0     # 單邊手續費 TWD
FUTURES_TAX_RATE = 0.00002  # 期貨交易稅 (0.002%)
OPTIONS_TAX_RATE = 0.001    # 選擇權交易稅 (0.1%)

FILE_PATH = "data/txf_options_backtest.csv"

def fetch_and_process_data():
    print("🚀 啟動專業級摩擦成本回測運算...")
    df = yf.download("^TWII", period="5y", interval="1d")
    if df.empty: return
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    df.dropna(inplace=True)

    # 1. 基礎技術指標與流動性評估
    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
    df['Avg_Vol'] = df['Volume'].rolling(20).mean() # 用於評估成交量
    
    # 2. 進出場價格設定 (加入滑價模擬)
    # 進場買在 Open + Slippage/2, 賣在 Open - Slippage/2
    df['Entry_Price_Buy'] = df['Open'].shift(-1) + (SLIPPAGE / 2)
    df['Entry_Price_Sell'] = df['Open'].shift(-1) - (SLIPPAGE / 2)
    
    # 10天後平倉 (考慮滑價)
    df['Exit_Price_10d_Sell'] = df['Close'].shift(-10) - (SLIPPAGE / 2)
    df['Exit_Price_10d_Buy'] = df['Close'].shift(-10) + (SLIPPAGE / 2)
    
    # 3. 大腦訊號生成 (保留原本 3L/MAD 框架)
    # ... (省略中間指標運算，確保與原本大腦邏輯一致) ...
    # 假設已生成 Signal_3L_Strict 等欄位

    # 4. 損益計算 (精確計算稅金與手續費)
    brains = ['3L_Strict', '3L_Relaxed', 'MAD', 'Dir']
    for b in brains:
        sig = f'Signal_{b}'
        pos = 1.0 # 預設口數
        
        # A. 點數盈虧 (扣除滑價後的點數差)
        pts = np.where(df[sig] == 1, df['Exit_Price_10d_Sell'] - df['Entry_Price_Buy'],
              np.where(df[sig] == -1, df['Entry_Price_Sell'] - df['Exit_Price_10d_Buy'], 0))
        
        # B. 交易成本計算 (微台 10元/點)
        # 總交易口數 = 進場 + 出場 (若有訊號則為 2 口單邊交易)
        trade_count = np.where(df[sig] != 0, 2, 0)
        total_comm = trade_count * COMMISSION
        
        # 稅金 (以微台為例：點數 * 10元 * 稅率)
        # 進場稅 + 出場稅
        tax_in = np.where(df[sig] != 0, df['Open'].shift(-1) * 10 * FUTURES_TAX_RATE, 0)
        tax_out = np.where(df[sig] != 0, df['Close'].shift(-10) * 10 * FUTURES_TAX_RATE, 0)
        
        # C. 淨損益 (TWD) = (點數盈虧 * 10) - 手續費 - 稅金
        df[f'{b}_Micro_PnL_TWD'] = (pts * 10 * pos) - total_comm - (tax_in + tax_out)

        # 考慮流動性 (成交量) 的動態滑價：若當日成交量低於 20 日平均 80%，損益額外扣除 1 點
        vol_penalty = np.where((df[sig] != 0) & (df['Volume'] < df['Avg_Vol'] * 0.8), 10 * pos, 0)
        df[f'{b}_Micro_PnL_TWD'] -= vol_penalty

    df.fillna(0).to_csv(FILE_PATH)
    print("✅ 摩擦成本數據更新完成。")

if __name__ == "__main__":
    fetch_and_process_data()
