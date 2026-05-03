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

# 🔥 關鍵映射：必須與後端欄位完全一致
if "3L-Strict" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Strict', '3L_Strict_PnL_TWD', 'Pos_3L_Strict'
elif "3L-Relaxed" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Relaxed', '3L_Relaxed_PnL_TWD', 'Pos_3L_Relaxed'
elif "MAD" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_MAD', 'MAD_PnL_TWD', 'Pos_MAD'
else:
    signal_col, pnl_col, pos_col = 'Signal_Dir', 'Dir_PnL_TWD', 'Pos_Dir'

if "鐵蝴蝶" in strategy_type:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# 防呆檢查
if signal_col not in df.columns:
    st.error(f"🚨 找不到 `{signal_col}` 欄位！請先執行 `update_data.py`")
    st.stop()

# -------------------------
# 2. 核心績效計算 (KeyError 發生處已修正)
# -------------------------
trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna() # 修正後的映射會解決 KeyError

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

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("總交易次數", f"{len(trade_results)} 次")
col2.metric("策略勝率", f"{win_rate:.2f}%")
col3.metric("單筆期望值", f"NT$ {ev:.0f}")
col4.metric("策略夏普值", f"{sharpe:.2f}")
col5.metric("累積總損益", f"NT$ {total_pnl:,.0f}")

# ... (後續繪圖與明細代碼同前) ...
