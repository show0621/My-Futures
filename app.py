import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(page_title="台指選擇權回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

df = load_data()

st.title("📈 台指選擇權 60K 全方位回測系統")

if df.empty:
    st.warning("⚠️ 尚未找到資料，請先執行 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 策略選擇區塊
# -------------------------
strategy_choice = st.sidebar.radio(
    "⚙️ 選擇回測策略",
    ("波段方向策略 (Long Call/Put)", "中性盤整策略 (鐵蝴蝶 Iron Butterfly)")
)

# 根據選擇動態切換使用的欄位
if "波段方向策略" in strategy_choice:
    signal_col = 'Signal_Dir'
    pnl_col = 'Dir_PnL_TWD'
    st.header("趨勢波段策略分析")
    st.caption("進場邏輯：MACD 交叉配合均線濾網。執行：次根 K 棒開盤價進場。")
else:
    signal_col = 'Signal_IB'
    pnl_col = 'IB_PnL_TWD'
    st.header("🦋 鐵蝴蝶中性策略分析")
    st.caption("進場邏輯：高波動且動能衰退時建倉。架構：依進場點與當前 ATR 自動決定翅膀寬度。")

# -------------------------
# 2. 核心績效計算 (包含累積損益)
# -------------------------
trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    std_dev = trade_results.std()
    sharpe = (ev / std_dev) * np.sqrt(252) if std_dev != 0 else 0
    # 計算累積損益
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
# 3. 繪製累積損益圖與 K 線圖
# -------------------------
st.subheader("💰 累積損益曲線")
if len(trades) > 0:
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], 
                                 mode='lines', fill='tozeroy', name='累積損益(TWD)', 
                                 line=dict(color='rgba(255, 165, 0, 0.8)')))
    fig_pnl.update_layout(height=300, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位 (以進場開盤價為基準)")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index,
                open=plot_df['Open'], high=plot_df['High'],
                low=plot_df['Low'], close=plot_df['Close'], name="60K K線")])

# 標示買點 (注意：改標示在 Entry_Price 上，這才是真實進場點)
buy_signals = plot_df[plot_df[signal_col] == 1]
fig_k.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Entry_Price'],
                         mode='markers+text', marker=dict(symbol='triangle-up', color='red', size=14),
                         name='作多/建倉', text=buy_signals['Position_Size'].astype(int).astype(str) + " 口",
                         textposition="bottom center"))

sell_signals = plot_df[plot_df[signal_col] == -1]
if len(sell_signals) > 0:
    fig_k.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['Entry_Price'],
                             mode='markers+text', marker=dict(symbol='triangle-down', color='green', size=14),
                             name='放空', text=sell_signals['Position_Size'].astype(int).astype(str) + " 口",
                             textposition="top center"))

fig_k.update_layout(height=500, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細與下載
# -------------------------
st.subheader("📋 交易紀錄明細 (OHLCV 實戰評估)")
display_cols = ['Open', 'Close', 'Volume', 'ATR', signal_col, 'Position_Size', 'Entry_Price', 'Exit_Price', pnl_col, 'Cumulative_PnL']

if not trades.empty:
    st.dataframe(trades[display_cols].sort_index(ascending=False).style.format({
        'Open': '{:.0f}', 'Close': '{:.0f}', 'Entry_Price': '{:.0f}', 'Exit_Price': '{:.0f}',
        'ATR': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
    }))

csv = df.to_csv().encode('utf-8-sig')
st.download_button(
    label="📥 下載包含 OHLCV 的完整回測 CSV 資料",
    data=csv,
    file_name='txf_advanced_backtest.csv',
    mime='text/csv',
)
