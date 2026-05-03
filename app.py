import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- 最高指導原則：框架完整、功能找回、視覺真實 ---
st.set_page_config(page_title="台指期權專業回測系統", layout="wide")

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df, None
    return pd.DataFrame(), "ERR-101"

raw_df, init_err = load_data()

st.title("📈 台指期權量化回測系統 (專業全功能版)")

# -------------------------
# 1. 側邊欄設定
# -------------------------
st.sidebar.header("⚙️ 引擎與期間")
if init_err:
    st.error(f"🚨 系統診斷: {init_err} (找不到資料檔案)")
    st.stop()

max_date = raw_df.index.max()
start_date = st.sidebar.date_input("回測開始日期", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("回測結束日期", value=max_date)

# 時區對齊
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

# 映射配置
b_map = {"法人 3L-Strict (0.33門檻)": "3L_Strict", "法人 3L-Relaxed (0門檻)": "3L_Relaxed", "MAD 均線距離策略": "MAD", "基礎指標模型 (MACD/ATR)": "Dir"}
t_map = {"純微台期 (10元/點)": "Micro", "期貨 + 選擇權賣方 (收租型)": "Seller", "純買方 (Long Call/Put)": "Buy", "價差策略 (Bull/Bear Spread)": "Spread"}

engine_choice = st.sidebar.selectbox("1. 選擇決策大腦", list(b_map.keys()))
strategy_choice = st.sidebar.radio("2. 選擇操作工具", list(t_map.keys()))
use_rm = st.sidebar.checkbox("開啟 ATR 風控與 7 天平倉", value=True)

b_prefix = b_map.get(engine_choice)
t_prefix = t_map.get(strategy_choice)
rm_suffix = "_RM" if use_rm else ""

pnl_col = f"{b_prefix}_{t_prefix}{rm_suffix}_PnL_TWD"
signal_col = f"Signal_{b_prefix}"
pos_col = f"Pos_{b_prefix}"

# -------------------------
# 2. 績效看板 (找回所有功能)
# -------------------------
if pnl_col not in df.columns:
    st.error(f"🚨 診斷代碼: ERR-202 (缺失欄位: {pnl_col})")
    st.stop()

trades = df[df[signal_col] != 0].copy()
if not trades.empty:
    trade_results = trades[pnl_col].dropna()
    trades['Cum_PnL'] = trade_results.cumsum()
    
    # 績效指標計算
    sharpe = (trade_results.mean() / trade_results.std() * np.sqrt(252)) if trade_results.std() != 0 else 0
    mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()

    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總交易次數", f"{len(trade_results)} 次")
    c2.metric("策略勝率", f"{(len(trade_results[trade_results>0])/len(trade_results)*100):.1f}%")
    c3.metric("策略夏普值", f"{sharpe:.2f}")
    c4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
    c5.metric("累積總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")

    # -------------------------
    # 3. 圖表渲染 (損益在上，K棒在下)
    # -------------------------
    st.subheader("💰 累積損益曲線 (Equity Curve)")
    fig_pnl = go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], mode='lines', fill='tozeroy', line=dict(color='#00FFCC'))])
    fig_pnl.update_layout(height=350, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_pnl, use_container_width=True)

    st.subheader("📊 走勢標示 (專業交易終端模式 - 日K)")
    plot_df = df.tail(150) # 限制顯示根數確保 K 棒飽滿
    
    fig_k = go.Figure()
    # 主 K 線：使用 category 軸強制移除週末，使 K 棒真實飽滿
    fig_k.add_trace(go.Candlestick(
        x=plot_df.index.strftime('%Y-%m-%d'),
        open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
        increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
        increasing_fillcolor='#FF3232', decreasing_fillcolor='#32FF32',
        name="台指日K"
    ))

    # 訊號標示 (偏移避讓)
    for s, c, sym, ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -200), (-1, '#00F0FF', 'triangle-down', 'High', 200)]:
        sigs = plot_df[plot_df[signal_col] == s]
        if not sigs.empty:
            fig_k.add_trace(go.Scatter(
                x=sigs.index.strftime('%Y-%m-%d'), y=sigs[ref] + offset,
                mode='markers+text',
                marker=dict(symbol=sym, color=c, size=15),
                text=sigs[pos_col].astype(int).astype(str) + "口",
                textposition="bottom center" if s == 1 else "top center",
                name="進場訊號"
            ))

    fig_k.update_layout(
        height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
        xaxis=dict(type='category', nticks=20, tickangle=-45, gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(side="right", gridcolor='rgba(255,255,255,0.05)'),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    st.plotly_chart(fig_k, use_container_width=True)

# 4. 下載與明細
st.subheader("📋 交易明細紀錄")
st.dataframe(trades[['Close', 'YZ_Vol', 'Composite_Score', pnl_col, 'Cum_PnL']].sort_index(ascending=False).style.format("{:.0f}"))
st.sidebar.download_button("📥 下載數據 CSV", df.to_csv().encode('utf-8-sig'), "backtest.csv")
