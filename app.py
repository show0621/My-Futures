import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- [最高指導原則] 功能回歸、順序校正、視覺真實 ---
st.set_page_config(page_title="台指期權回測系統", layout="wide")

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
    st.error(f"🚨 錯誤代碼: {init_err} (找不到 CSV)")
    st.stop()

max_date = raw_df.index.max()
start_date = st.sidebar.date_input("回測開始", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("回測結束", value=max_date)

ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

# 映射邏輯 (嚴格對齊)
brain_list = ["法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)"]
tool_list = ["純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)"]

engine_choice = st.sidebar.selectbox("1. 選擇大腦", brain_list)
strategy_choice = st.sidebar.radio("2. 選擇工具", tool_list)
use_rm = st.sidebar.checkbox("開啟 ATR 風控與 7 天平倉", value=True)

b_map = {"法人 3L-Strict (0.33門檻)": "3L_Strict", "法人 3L-Relaxed (0門檻)": "3L_Relaxed", "MAD 均線距離策略": "MAD", "基礎指標模型 (MACD/ATR)": "Dir"}
t_map = {"純微台期 (10元/點)": "Micro", "期貨 + 選擇權賣方 (收租型)": "Seller", "純買方 (Long Call/Put)": "Buy", "價差策略 (Bull/Bear Spread)": "Spread"}

b_prefix = b_map.get(engine_choice)
t_prefix = t_map.get(strategy_choice)
rm_suffix = "_RM" if use_rm else ""

pnl_col = f"{b_prefix}_{t_prefix}{rm_suffix}_PnL_TWD"
signal_col = f"Signal_{b_prefix}"
pos_col = f"Pos_{b_prefix}"

if "鐵蝴蝶" in strategy_choice:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# -------------------------
# 2. 診斷與績效看板
# -------------------------
st.header("🔍 即時診斷與目前操作建議")
if not df.empty:
    last = df.iloc[-1]
    score = last.get('Composite_Score', 0)
    diag = "🔥 多頭持續" if score >= 0.66 else "🚀 多頭開始" if score > 0 else "❄️ 空頭持續" if score <= -0.66 else "🔄 盤整震盪"
    
    d1, d2, d3 = st.columns(3)
    d1.metric("當前盤勢", diag)
    d2.metric("關鍵支撐 / 壓力", f"{df['Low'].tail(60).min():.0f} / {df['High'].tail(60).max():.0f}")
    d3.metric("建議口數", f"{int(last.get(pos_col, 0))} 口" if last.get(signal_col,0) != 0 else "觀望")

if pnl_col not in df.columns:
    st.error(f"🚨 診斷代碼: ERR-202 (缺失欄位: {pnl_col})")
    st.stop()

# 績效計算
trades = df[df[signal_col] != 0].copy()
if not trades.empty:
    trade_results = trades[pnl_col].dropna()
    trades['Cum_PnL'] = trade_results.cumsum()
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
    # 3. 圖表顯示 (順序校正)
    # -------------------------
    # (1) 損益曲線在上
    st.subheader("💰 累積損益曲線")
    fig_pnl = go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], mode='lines', fill='tozeroy', line=dict(color='#00FFCC'))])
    fig_pnl.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_pnl, use_container_width=True)

    # (2) 專業 K 線在下 (視覺優化)
    st.subheader("📊 走勢標示 (專業交易終端模式)")
    # 為了畫面飽滿，取回測區間的最近 120 天
    plot_df = df.tail(120)
    
    fig_k = go.Figure()
    fig_k.add_trace(go.Candlestick(
        x=plot_df.index.strftime('%Y-%m-%d'), # 改為字串格式搭配 category 軸
        open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
        increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
        increasing_fillcolor='#FF3232', decreasing_fillcolor='#32FF32',
        name="台指日K"
    ))

    # 訊號位移標示
    for s, c, sym, ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -150), (-1, '#00F0FF', 'triangle-down', 'High', 150)]:
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

# 4. 明細
st.subheader("📋 交易明細紀錄")
st.dataframe(trades[['Close', 'YZ_Vol', 'Composite_Score', pnl_col, 'Cum_PnL']].sort_index(ascending=False).style.format("{:.0f}"))
st.sidebar.download_button("📥 下載數據 CSV", df.to_csv().encode('utf-8-sig'), "backtest.csv")
