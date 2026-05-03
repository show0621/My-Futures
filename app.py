import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(page_title="台指期權量化終端", layout="wide")

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        return pd.read_csv(file_path, index_col=0, parse_dates=True)
    return pd.DataFrame()

df_raw = load_data()

st.title("📈 台指期權量化回測系統 (專業全功能版)")

if df_raw.empty:
    st.error("🚨 找不到 CSV 檔案，請確認 GitHub Actions 已執行。")
    st.stop()

# -------------------------
# 1. 側邊欄與策略選擇
# -------------------------
st.sidebar.header("⚙️ 設定")
engine_choice = st.sidebar.selectbox("大腦", ("3L_Strict", "3L_Relaxed", "MAD", "Dir"))
pnl_col = f"{engine_choice}_Micro_PnL_TWD"
sig_col = f"Signal_{engine_choice}"

# -------------------------
# 2. 核心指標看板 (夏普值 & MDD)
# -------------------------
trades = df_raw[df_raw[sig_col] != 0].copy()

if not trades.empty:
    # 績效計算
    pnl = trades[pnl_col]
    trades['Cum_PnL'] = pnl.cumsum()
    sharpe = (pnl.mean() / pnl.std() * np.sqrt(252)) if pnl.std() != 0 else 0
    mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()

    st.subheader("📊 策略績效摘要")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("交易次數", f"{len(trades)} 次")
    m2.metric("勝率", f"{(len(pnl[pnl>0])/len(trades)*100):.1f}%")
    m3.metric("夏普值", f"{sharpe:.2f}")
    m4.metric("最大回撤 ($MDD$)", f"NT$ {mdd:,.0f}")
    m5.metric("總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")

    # -------------------------
    # 3. 專業 K 線圖 (含放空、平倉標示)
    # -------------------------
    st.subheader("🔍 走勢與訊號標示")
    plot_df = df_raw.tail(120)
    fig = go.Figure(data=[go.Candlestick(
        x=plot_df.index.strftime('%Y-%m-%d'),
        open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
        increasing_line_color='#FF3232', decreasing_line_color='#32FF32', name="日K"
    )])

    # 進場標示 (做多與放空)
    for s, c, sym, name in [(1, '#FFD700', 'triangle-up', '做多'), (-1, '#00F0FF', 'triangle-down', '放空')]:
        target = plot_df[plot_df[sig_col] == s]
        if not target.empty:
            fig.add_trace(go.Scatter(
                x=target.index.strftime('%Y-%m-%d'), 
                y=np.where(s==1, target['Low']-100, target['High']+100),
                mode='markers', marker=dict(symbol=sym, color=c, size=12), name=name
            ))

    # 平倉標示 (防禦性讀取，避免 KeyError)
    if 'Exit_Date_10d' in plot_df.columns:
        exit_sigs = plot_df[plot_df[sig_col] != 0]
        fig.add_trace(go.Scatter(
            x=exit_sigs['Exit_Date_10d'], y=exit_sigs['Exit_Price_10d'],
            mode='markers', marker=dict(symbol='circle', color='white', size=7), name='平倉'
        ))

    fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False, xaxis={'type': 'category'})
    st.plotly_chart(fig, use_container_width=True)

# -------------------------
# 4. 買賣明細表 (找回消失的功能)
# -------------------------
st.subheader("📋 買賣明細紀錄")
if not trades.empty:
    display_df = trades[['Close', pnl_col, 'Cum_PnL']].sort_index(ascending=False)
    st.dataframe(display_df.style.format("NT$ {:,.0f}"))
else:
    st.info("目前區間尚無交易紀錄。")
