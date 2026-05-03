import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

# 設定網頁標題與寬度
st.set_page_config(page_title="台指選擇權法人級回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

df = load_data()

st.title("📈 台指選擇權全方位回測系統 (含價差策略實證)")

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
    ("純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# --- 動態欄位映射 ---
if "3L-Strict" in engine_choice:
    prefix, pos_col = '3L_Strict', 'Pos_3L_Strict'
    signal_col = 'Signal_3L_Strict'
elif "3L-Relaxed" in engine_choice:
    prefix, pos_col = '3L_Relaxed', 'Pos_3L_Relaxed'
    signal_col = 'Signal_3L_Relaxed'
elif "MAD" in engine_choice:
    prefix, pos_col = 'MAD', 'Pos_MAD'
    signal_col = 'Signal_MAD'
else:
    prefix, pos_col = 'Dir', 'Pos_Dir'
    signal_col = 'Signal_Dir'

# 根據操作策略切換損益欄位
if "純買方" in strategy_type:
    pnl_col = f"{prefix}_PnL_TWD"
    desc = "純買方策略：追求高槓桿爆發力，適合趨勢極其明確時。"
elif "價差策略" in strategy_type:
    pnl_col = f"{prefix}_Spread_PnL_TWD"
    desc = "價差策略：透過賣出遠端合約降低成本與 Theta 消耗，曲線較平穩。"
else:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'
    desc = "中性策略：預期市場波動收斂。"

st.header(f"當前執行：{engine_choice} - {strategy_type}")
st.caption(desc)

# -------------------------
# 2. 核心績效計算
# -------------------------
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 找不到欄位 `{pnl_col}`！請先手動觸發 GitHub Actions 更新 `update_data.py`。")
    st.stop()

trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    sharpe = (ev / trade_results.std()) * np.sqrt(252) if trade_results.std() != 0 else 0
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

# -------------------------
# 3. 繪製圖表
# -------------------------
st.subheader("💰 累積損益曲線")
if len(trades) > 0:
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], mode='lines', fill='tozeroy', name='累積損益(TWD)'))
    fig_pnl.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位標示")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="台指K線")])

for s, c, name, sym in [(1, 'red', '多頭佈局', 'triangle-up'), (-1, 'green', '空頭佈局', 'triangle-down')]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(x=sigs.index, y=sigs['Entry_Price'], mode='markers+text', marker=dict(symbol=sym, color=c, size=14), name=name, text=sigs[pos_col].astype(int).astype(str) + " 組"))

fig_k.update_layout(height=550, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細
# -------------------------
st.subheader("📋 交易明細")
display_cols = ['Close', 'YZ_Vol', 'Composite_Score', signal_col, pos_col, pnl_col, 'Cumulative_PnL']
if not trades.empty:
    st.dataframe(trades[display_cols].sort_index(ascending=False).style.format({
        'Close': '{:.0f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
    }))
