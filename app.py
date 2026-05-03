import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(page_title="台指選擇權法人級回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

df = load_data()

st.title("📈 台指選擇權全方位回測系統 (多空雙向實證版)")

if df.empty:
    st.warning("⚠️ 尚未找到資料，請先執行 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 策略選擇區塊
# -------------------------
st.sidebar.header("⚙️ 交易引擎設定")

engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦 (邏輯核心)",
    ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)")
)

strategy_type = st.sidebar.radio(
    "2. 選擇操作策略",
    ("方向波段 (買方 Long Call/Put 多空雙向)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# 根據選單設定對應的欄位名稱
if "3L-Strict" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Strict', '3L_Strict_PnL_TWD', 'Pos_3L_Strict'
elif "3L-Relaxed" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Relaxed', '3L_Relaxed_PnL_TWD', 'Pos_3L_Relaxed'
elif "MAD" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_MAD', 'MAD_PnL_TWD', 'Pos_MAD'
else:
    signal_col, pnl_col, pos_col = 'Signal_Dir', 'Dir_PnL_TWD', 'Pos_Dir'

# 鐵蝴蝶覆蓋
if "鐵蝴蝶" in strategy_type:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# 再次檢查欄位是否存在
if signal_col not in df.columns:
    st.error(f"🚨 找不到 `{signal_col}` 欄位！請先在 GitHub 手動執行 `Run workflow` 更新資料。")
    st.stop()

# -------------------------
# 2. 核心績效計算
# -------------------------
trades = df[df[signal_col] != 0].copy()
# 確保 pnl_col 不會導致 KeyError
if pnl_col not in trades.columns:
    st.error(f"🚨 找不到損益欄位 `{pnl_col}`，請檢查 CSV 是否為最新版本。")
    st.stop()

trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    std_dev = trade_results.std()
    sharpe = (ev / std_dev) * np.sqrt(252) if std_dev != 0 else 0
    trades['Cumulative_PnL'] = trades[pnl_col].cumsum()
    total_pnl = trades['Cumulative_PnL'].iloc[-1]
else:
    win_rate = ev = sharpe = total_pnl = 0
    trades['Cumulative_PnL'] = 0

# -------------------------
# 3. 圖表與明細 (省略重複繪圖代碼)
# -------------------------
# ... 同前版本 ...
