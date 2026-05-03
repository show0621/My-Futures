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

st.title("📈 台指選擇權 60K 全方位回測系統 (含法人三層式模型)")

if df.empty:
    st.warning("⚠️ 尚未找到資料，請先執行 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 雙層策略選擇區塊
# -------------------------
st.sidebar.header("⚙️ 交易引擎設定")

engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦 (邏輯核心)",
    ("基礎指標模型 (MACD/ATR)", "法人三層式模型 (動能/YZ波動率)")
)

strategy_choice = st.sidebar.radio(
    "2. 選擇操作策略 (買方/中性)",
    ("方向波段 (買方 Long Call/Put)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# 動態配置對應的欄位
if engine_choice == "基礎指標模型 (MACD/ATR)":
    if "方向波段" in strategy_choice:
        signal_col, pnl_col, pos_col = 'Signal_Dir', 'Dir_PnL_TWD', 'Pos_Dir'
        desc = "進場邏輯：MACD 交叉配合均線濾網。資金控管：依賴單純 ATR。"
    else:
        signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'
        desc = "進場邏輯：高波動且動能衰退時建倉。資金控管：依賴單純 ATR。"
else:
    if "方向波段" in strategy_choice:
        signal_col, pnl_col, pos_col = 'Signal_3L_Dir', '3L_Dir_PnL_TWD', 'Pos_3L_Dir'
        desc = "進場邏輯：20/60/120 多重時間框架共振。資金控管：目標 30% 波動率 + Yang-Zhang 槓桿縮放。"
    else:
        signal_col, pnl_col, pos_col = 'Signal_3L_IB', '3L_IB_PnL_TWD', 'Pos_3L_IB'
        desc = "進場邏輯：趨勢分歧(死魚盤)且 YZ 波動率收斂時進場。資金控管：目標 30% 波動率放大槓桿。"

st.header(f"當前執行：{engine_choice} - {strategy_choice}")
st.caption(desc)

# 🔥 防呆檢查機制
if signal_col not in df.columns:
    st.error(f"🚨 在資料中找不到 `{signal_col}` 欄位！請先到終端機執行 `python update_data.py` (或觸發 GitHub Actions) 產生最新資料。")
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
# 3. 繪製圖表
# -------------------------
st.subheader("💰 累積損益曲線")
if len(trades) > 0:
    fig_pnl = go.Figure()
    color = 'rgba(50, 205, 50, 0.8)' if '法人' in engine_choice else 'rgba(255, 165, 0, 0.8)'
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], mode='lines', fill='tozeroy', name='累積損益(TWD)', line=dict(color=color)))
    fig_pnl.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位 (以開盤價進場)")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="60K K線")])

buy_signals = plot_df[plot_df[signal_col] == 1]
fig_k.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Entry_Price'], mode='markers+text', marker=dict(symbol='triangle-up', color='red', size=14), name='作多/建倉', text=buy_signals[pos_col].astype(int).astype(str) + " 口", textposition="bottom center"))

sell_signals = plot_df[plot_df[signal_col] == -1]
if len(sell_signals) > 0:
    fig_k.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['Entry_Price'], mode='markers+text', marker=dict(symbol='triangle-down', color='green', size=14), name='放空', text=sell_signals[pos_col].astype(int).astype(str) + " 口", textposition="top center"))

fig_k.update_layout(height=500, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細
# -------------------------
st.subheader("📋 交易紀錄明細")

# 若選擇法人引擎，則多顯示 YZ_Vol 與 Composite_Score 讓你看清楚模型如何運作
if "法人" in engine_choice:
    display_cols = ['Close', 'YZ_Vol', 'Composite_Score', 'Risk_Leverage', signal_col, pos_col, pnl_col, 'Cumulative_PnL']
else:
    display_cols = ['Close', 'ATR', signal_col, pos_col, pnl_col, 'Cumulative_PnL']

if not trades.empty:
    st.dataframe(trades[display_cols].sort_index(ascending=False).style.format({
        'Close': '{:.0f}', 'ATR': '{:.2f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', 'Risk_Leverage': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
    }))
