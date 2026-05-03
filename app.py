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

st.title("📈 台指選擇權全方位回測系統 (多策略實證版)")

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
    ("方向波段 (買方 Long Call/Put)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# 動態欄位映射
if "3L-Strict" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Strict', '3L_Strict_PnL', 'Pos_3L_Strict'
    desc = "法人嚴格版：僅在 20/60/120 日趨勢高度共振 (>= 0.33) 時執行 MACD 扳機。"
elif "3L-Relaxed" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_3L_Relaxed', '3L_Relaxed_PnL', 'Pos_3L_Relaxed'
    desc = "法人寬鬆版：只要長線趨勢為正 (> 0) 即允許 MACD 扳機進場，增加交易頻率。"
elif "MAD" in engine_choice:
    signal_col, pnl_col, pos_col = 'Signal_MAD', 'MAD_PnL', 'Pos_MAD'
    desc = "MAD 策略：監控價格與 20MA 的距離。在長線看多下，捕捉過度乖離的回檔買點。"
else:
    signal_col, pnl_col, pos_col = 'Signal_Dir', 'Dir_PnL_TWD', 'Pos_Dir'
    desc = "基礎模型：單純以 MACD 交叉與 100MA 判斷方向。"

# 若選擇鐵蝴蝶，則覆蓋欄位
if "鐵蝴蝶" in strategy_type:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'
    desc = "中性策略：預期市場進入盤整。依據 ATR 自動調整蝴蝶翅膀範圍。"

st.header(f"當前執行：{engine_choice}")
st.caption(desc)

if signal_col not in df.columns:
    st.error(f"🚨 找不到 `{signal_col}` 欄位！請先執行更新程式。")
    st.stop()

# -------------------------
# 2. 核心績效計算
# -------------------------
trades = df[df[signal_col] != 0].copy()
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

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("總交易次數", f"{len(trade_results)} 次")
col2.metric("策略勝率", f"{win_rate:.2f}%")
col3.metric("單筆期望值", f"NT$ {ev:.0f}")
col4.metric("策略夏普值", f"{sharpe:.2f}")
col5.metric("累積總損益", f"NT$ {total_pnl:,.0f}")

# -------------------------
# 3. 繪製圖表 (累積損益 & K線)
# -------------------------
st.subheader("💰 累積損益曲線")
if len(trades) > 0:
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], mode='lines', fill='tozeroy', name='累積損益(TWD)'))
    fig_pnl.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位 (以開盤價進場)")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="60K K線")])

for s, c, name in [(1, 'red', '買入'), (-1, 'green', '賣出')]:
    sigs = plot_df[plot_df[signal_col] == s]
    fig_k.add_trace(go.Scatter(x=sigs.index, y=sigs['Entry_Price'], mode='markers+text', marker=dict(symbol='triangle-up' if s==1 else 'triangle-down', color=c, size=14), name=name, text=sigs[pos_col].astype(int).astype(str) + " 口", textposition="bottom center"))

fig_k.update_layout(height=500, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細
# -------------------------
st.subheader("📋 交易紀錄明細")
cols = ['Close', 'YZ_Vol', 'Composite_Score', 'MAD_Value', signal_col, pos_col, pnl_col, 'Cumulative_PnL']
st.dataframe(trades[cols].sort_index(ascending=False).style.format({
    'Close': '{:.0f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', 'MAD_Value': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
}))
