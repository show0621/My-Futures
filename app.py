import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(page_title="台指期權專業回測終端", layout="wide")

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        return pd.read_csv(file_path, index_col=0, parse_dates=True), None
    return pd.DataFrame(), "ERR-101"

raw_df, err = load_data()

st.title("📈 台指期權量化回測系統 (專業全功能版)")

# -------------------------
# 1. 績效指標看板 (保留夏普、MDD 等核心框架)
# -------------------------
b_prefix, t_prefix = "3L_Strict", "Micro"
pnl_col, sig_col = f"{b_prefix}_{t_prefix}_PnL_TWD", f"Signal_{b_prefix}"

if pnl_col not in raw_df.columns:
    st.error(f"🚨 錯誤代碼: ERR-202 (缺失欄位: {pnl_col})")
    st.stop()

trades = raw_df[raw_df[sig_col] != 0].copy()
if not trades.empty:
    trade_results = trades[pnl_col]
    trades['Cum_PnL'] = trade_results.cumsum()
    sharpe = (trade_results.mean() / trade_results.std() * np.sqrt(252)) if trade_results.std() != 0 else 0
    mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總交易次數", f"{len(trades)} 次")
    c2.metric("勝率", f"{(len(trade_results[trade_results>0])/len(trades)*100):.1f}%")
    c3.metric("夏普值", f"{sharpe:.2f}")
    c4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
    c5.metric("累積總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")

# -------------------------
# 2. 圖表佈局：損益在上，K線在下
# -------------------------
# (1) 累積損益曲線
st.subheader("💰 累積損益曲線")
fig_pnl = go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], mode='lines', fill='tozeroy', line=dict(color='#00FFCC'))])
fig_pnl.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_pnl, use_container_width=True)

# (2) 專業日 K 走勢與全訊號標示
st.subheader("📊 走勢標示 (含進場、放空、平倉)")
plot_df = raw_df.tail(150) # 顯示最近 150 天確保飽滿

fig_k = go.Figure()
# 日 K 線
fig_k.add_trace(go.Candlestick(
    x=plot_df.index.strftime('%Y-%m-%d'),
    open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
    increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
    name="台指日K"
))

# 標示邏輯：做多(黃色)、放空(青色)、平倉(白色)
for s, c, sym, name in [(1, '#FFD700', 'triangle-up', '做多進場'), (-1, '#00F0FF', 'triangle-down', '放空進場')]:
    sigs = plot_df[plot_df[sig_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=sigs.index.strftime('%Y-%m-%d'), 
            y=np.where(s==1, sigs['Low']-150, sigs['High']+150),
            mode='markers', marker=dict(symbol=sym, color=c, size=15), name=name
        ))

# 平倉訊號 (根據 Entry Date 找 10 天後的日期標示)
exit_sigs = plot_df[plot_df[sig_col] != 0]
if not exit_sigs.empty:
    fig_k.add_trace(go.Scatter(
        x=pd.to_datetime(exit_sigs['Exit_Date_10d']).dt.strftime('%Y-%m-%d'),
        y=exit_sigs['Exit_Price_10d'],
        mode='markers', marker=dict(symbol='circle', color='white', size=8, line=dict(width=1)),
        name='平倉位置'
    ))

fig_k.update_layout(
    height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
    xaxis=dict(type='category', nticks=20), yaxis=dict(side="right"),
    margin=dict(l=10, r=10, t=30, b=10)
)
st.plotly_chart(fig_k, use_container_width=True)
