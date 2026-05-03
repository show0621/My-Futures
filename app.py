import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- 框架回歸：指標看板、診斷區、全訊號標示、明細表 ---
st.set_page_config(page_title="台指期權量化終端", layout="wide")

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        return pd.read_csv(file_path, index_col=0, parse_dates=True)
    return pd.DataFrame()

df_raw = load_data()

st.title("📈 台指期權全功能回測系統 (專業版)")

if df_raw.empty:
    st.error("🚨 找不到資料庫。請確認 GitHub Actions 成功。")
    st.stop()

# -------------------------
# 1. 側邊欄設定
# -------------------------
st.sidebar.header("⚙️ 設定與期間")
max_date = df_raw.index.max()
start_date = st.sidebar.date_input("開始日期", max_date - timedelta(days=365))
end_date = st.sidebar.date_input("結束日期", max_date)

engine_choice = st.sidebar.selectbox("1. 選擇大腦", ("3L_Strict", "3L_Relaxed", "MAD", "Dir"))
use_rm = st.sidebar.checkbox("開啟 ATR 風控 (7天平倉)", value=True)

# 映射配置
rm_suffix = "_RM" if use_rm else ""
pnl_col = f"{engine_choice}_Micro{rm_suffix}_PnL_TWD"
sig_col = f"Signal_{engine_choice}"
pos_col = f"Pos_{engine_choice}"

# -------------------------
# 2. 即時診斷與建議
# -------------------------
st.header("🔍 即時診斷與操作建議")
last = df_raw.iloc[-1]
score = last.get('Composite_Score', 0)
diag = "🔥 多頭持續" if score > 0.5 else "🚀 多頭發動" if score > 0 else "❄️ 空頭持續" if score < -0.5 else "🔄 盤整震盪"
support, resistance = df_raw['Low'].tail(60).min(), df_raw['High'].tail(60).max()

d1, d2, d3 = st.columns(3)
d1.metric("當前盤勢診斷", diag)
d2.metric("支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
d3.metric("建議口數", f"{int(last.get(pos_col, 0))} 口" if last.get(sig_col, 0) != 0 else "觀望")

# -------------------------
# 3. 核心績效看板 (夏普值 & MDD)
# -------------------------
ts_start, ts_end = pd.Timestamp(start_date).tz_localize(df_raw.index.tz), pd.Timestamp(end_date).tz_localize(df_raw.index.tz)
df = df_raw.loc[ts_start:ts_end].copy()
trades = df[df[sig_col] != 0].copy()

if not trades.empty:
    pnl = trades[pnl_col]
    trades['Cum_PnL'] = pnl.cumsum()
    sharpe = (pnl.mean() / pnl.std() * np.sqrt(252)) if pnl.std() != 0 else 0
    mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()

    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("交易次數", f"{len(trades)} 次")
    m2.metric("勝率", f"{(len(pnl[pnl>0])/len(trades)*100):.1f}%")
    m3.metric("策略夏普值", f"{sharpe:.2f}")
    m4.metric("最大回撤 ($MDD$)", f"NT$ {mdd:,.0f}")
    m5.metric("累積總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")

    # -------------------------
    # 4. 圖表佈局 (損益在上，K棒在下)
    # -------------------------
    st.subheader("💰 累積損益曲線")
    fig_p = go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], mode='lines', fill='tozeroy', line=dict(color='#00FFCC'))])
    fig_p.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_p, use_container_width=True)

    st.subheader("📊 專業日 K 走勢標示")
    plot_df = df.tail(150)
    fig_k = go.Figure()
    # 主 K 線
    fig_k.add_trace(go.Candlestick(
        x=plot_df.index.strftime('%Y-%m-%d'),
        open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
        increasing_line_color='#FF3232', decreasing_line_color='#32FF32', name="台指日K"
    ))
    # 訊號：多(黃)、空(青)、平倉(白圓)
    for s, c, sym, name in [(1, '#FFD700', 'triangle-up', '做多'), (-1, '#00F0FF', 'triangle-down', '放空')]:
        sigs = plot_df[plot_df[sig_col] == s]
        if not sigs.empty:
            fig_k.add_trace(go.Scatter(
                x=sigs.index.strftime('%Y-%m-%d'), y=np.where(s==1, sigs['Low']-150, sigs['High']+150),
                mode='markers', marker=dict(symbol=sym, color=c, size=15), name=name
            ))
    # 平倉點 (防禦性檢查)
    if 'Exit_Date_10d' in plot_df.columns:
        exits = plot_df[plot_df[sig_col] != 0]
        fig_k.add_trace(go.Scatter(
            x=exits['Exit_Date_10d' if not use_rm else 'Exit_Date_7d'], 
            y=exits['Exit_Price_10d' if not use_rm else 'Exit_Price_7d'],
            mode='markers', marker=dict(symbol='circle', color='white', size=8), name='平倉點'
        ))

    fig_k.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, xaxis={'type': 'category'})
    st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 5. 買賣明細紀錄
# -------------------------
st.subheader("📋 交易明細紀錄")
if not trades.empty:
    st.dataframe(trades[['Close', pnl_col, 'Cum_PnL']].sort_index(ascending=False).style.format("NT$ {:,.0f}"))
