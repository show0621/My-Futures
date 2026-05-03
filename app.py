import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

st.set_page_config(page_title="台指期權量化系統", layout="wide")

# 緩存機制修正：強制讀取最新資料
@st.cache_data(ttl=600)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        return pd.read_csv(file_path, index_col=0, parse_dates=True)
    return pd.DataFrame()

raw_df = load_data()

st.sidebar.header("🛠️ 系統工具")
debug_mode = st.sidebar.checkbox("開啟除錯模式 (顯示 CSV 欄位)")

if debug_mode:
    st.write("### 🔍 除錯資訊：CSV 欄位清單")
    st.write(raw_df.columns.tolist())

if raw_df.empty:
    st.warning("⚠️ 找不到資料。")
    st.stop()

# 1. 側邊欄設定
st.sidebar.header("⚙️ 引擎與期間")
max_date = raw_df.index.max()
start_date = st.sidebar.date_input("開始日期", max_date - timedelta(days=365))
end_date = st.sidebar.date_input("結束日期", max_date)

# 時區處理
ts_start, ts_end = pd.Timestamp(start_date), pd.Timestamp(end_date) + pd.Timedelta(hours=23)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

engine_map = {
    "法人 3L-Strict (0.33門檻)": "3L_Strict",
    "法人 3L-Relaxed (0門檻)": "3L_Relaxed",
    "MAD 均線距離策略": "MAD",
    "基礎指標模型 (MACD/ATR)": "Dir"
}
engine_choice = st.sidebar.selectbox("1. 選擇大腦", list(engine_map.keys()))
brain_prefix = engine_map[engine_choice]

strategy_map = {
    "純微台期 (10元/點)": "Micro",
    "期貨 + 選擇權賣方 (收租型)": "Seller",
    "純買方 (Long Call/Put)": "Buy",
    "價差策略 (Bull/Bear Spread)": "Spread"
}
strategy_choice = st.sidebar.radio("2. 選擇工具", list(strategy_map.keys()))
tool_prefix = strategy_map[strategy_choice]

st.sidebar.header("🛡️ 風險控管")
use_rm = st.sidebar.checkbox("開啟 ATR 風控 (2R/1R) 與 7天平倉")

# --- 映射組合 ---
rm_suffix = "_RM" if use_rm else ""
pnl_col = f"{brain_prefix}_{tool_prefix}{rm_suffix}_PnL_TWD"
signal_col = f"Signal_{brain_prefix}"
pos_col = f"Pos_{brain_prefix}"

# 下載按鈕
st.sidebar.divider()
st.sidebar.download_button("📥 下載目前 CSV", df.to_csv().encode('utf-8-sig'), "backtest.csv")

# -------------------------
# 2. 診斷與績效
# -------------------------
if not df.empty:
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    score = last.get('Composite_Score', 0)
    
    st.header(f"🔍 診斷：{engine_choice}")
    d1, d2, d3 = st.columns(3)
    d1.metric("目前盤勢", "🔥 多頭持續" if score > 0.33 else "❄️ 空頭持續" if score < -0.33 else "🔄 盤整")
    d2.metric("支撐 / 壓力", f"{df['Low'].tail(50).min():.0f} / {df['High'].tail(50).max():.0f}")
    
    # 檢查欄位是否存在
    if pnl_col in df.columns:
        trades = df[df[signal_col] != 0].copy()
        if not trades.empty:
            trades['Cum_PnL'] = trades[pnl_col].cumsum()
            total = trades['Cum_PnL'].iloc[-1]
            mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()
            
            p1, p2, p3 = st.columns(3)
            p1.metric("累積損益", f"NT$ {total:,.0f}")
            p2.metric("MDD (最大回撤)", f"NT$ {mdd:,.0f}")
            p3.metric("勝率", f"{(len(trades[trades[pnl_col]>0])/len(trades)*100):.1f}%")
            
            st.plotly_chart(go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], fill='tozeroy', name="權益曲線")]), use_container_width=True)
    else:
        st.error(f"❌ 找不到欄位：`{pnl_col}`。請開啟除錯模式檢查 CSV 標題。")

st.subheader("📊 近期進出場標示")
plot_df = df.tail(100)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'])])
st.plotly_chart(fig_k, use_container_width=True)
