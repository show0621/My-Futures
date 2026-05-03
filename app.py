import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- 核心框架：全功能回歸 ---
st.set_page_config(page_title="台指全方位回測系統", layout="wide")

ERROR_MAP = {
    "ERR-101": "資料庫缺失 (CSV)",
    "ERR-202": "策略映射失敗 (Column Missing)",
    "ERR-303": "目前區間無交易訊號"
}

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        return pd.read_csv(file_path, index_col=0, parse_dates=True), None
    return pd.DataFrame(), "ERR-101"

raw_df, err = load_data()

st.title("📈 台指期權量化回測系統 (專業全功能版)")

# -------------------------
# 1. 側邊欄與期間設定
# -------------------------
st.sidebar.header("⚙️ 引擎與期間")
if err:
    st.error(f"🚨 錯誤代碼: {err} ({ERROR_MAP.get(err)})")
    st.stop()

max_date = raw_df.index.max()
start_date = st.sidebar.date_input("開始日期", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("結束日期", value=max_date)

ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

engine_choice = st.sidebar.selectbox("1. 選擇大腦", ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)"))
strategy_choice = st.sidebar.radio("2. 選擇工具", ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)"))
use_rm = st.sidebar.checkbox("開啟 ATR 風控與 7 天平倉", value=True)

# 映射邏輯
b_map = {"法人 3L-Strict (0.33門檻)": "3L_Strict", "法人 3L-Relaxed (0門檻)": "3L_Relaxed", "MAD 均線距離策略": "MAD", "基礎指標模型 (MACD/ATR)": "Dir"}
t_map = {"純微台期 (10元/點)": "Micro", "期貨 + 選擇權賣方 (收租型)": "Seller", "純買方 (Long Call/Put)": "Buy", "價差策略 (Bull/Bear Spread)": "Spread"}

b_prefix, t_prefix = b_map.get(engine_choice), t_map.get(strategy_choice)
rm_suffix = "_RM" if use_rm else ""
pnl_col = f"{b_prefix}_{t_prefix}{rm_suffix}_PnL_TWD"
sig_col = f"Signal_{b_prefix}"
pos_col = f"Pos_{b_prefix}"

# -------------------------
# 2. 即時診斷與操作建議
# -------------------------
st.header("🔍 即時診斷與操作建議")
if not df.empty:
    last = df.iloc[-1]
    score = last.get('Composite_Score', 0)
    diag = "🔥 多頭持續" if score >= 0.66 else "🚀 多頭發動" if score > 0 else "❄️ 空頭持續" if score <= -0.66 else "🔄 盤整震盪"
    support, resistance = df['Low'].tail(60).min(), df['High'].tail(60).max()
    suggested_pos = int(last.get(pos_col, 0)) if last.get(sig_col,0) != 0 else 0

    d1, d2, d3 = st.columns(3)
    d1.metric("當前盤勢", diag)
    d2.metric("支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
    d3.metric("建議口數", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# -------------------------
# 3. 核心績效 (找回 夏普值 與 MDD)
# -------------------------
if pnl_col not in df.columns:
    st.error(f"🚨 錯誤代碼: ERR-202 (缺失欄位: {pnl_col})")
    st.stop()

trades = df[df[sig_col] != 0].copy()
if not trades.empty:
    trade_results = trades[pnl_col].dropna()
    trades['Cum_PnL'] = trade_results.cumsum()
    sharpe = (trade_results.mean() / trade_results.std() * np.sqrt(252)) if trade_results.std() != 0 else 0
    mdd = (trades['Cum_PnL'] - trades['Cum_PnL'].cummax()).min()

    st.divider()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("總交易次數", f"{len(trade_results)} 次")
    m2.metric("勝率", f"{(len(trade_results[trade_results>0])/len(trades)*100):.1f}%")
    m3.metric("夏普值", f"{sharpe:.2f}")
    m4.metric("最大回撤 ($MDD$)", f"NT$ {mdd:,.0f}")
    m5.metric("累積總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")

    # -------------------------
    # 4. 圖表佈局 (損益在上，K棒在下)
    # -------------------------
    st.subheader("💰 累積損益曲線")
    fig_pnl = go.Figure(data=[go.Scatter(x=trades.index, y=trades['Cum_PnL'], mode='lines', fill='tozeroy', line=dict(color='#00FFCC'))])
    fig_pnl.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_pnl, use_container_width=True)

    st.subheader("📊 走勢標示 (專業日K模式)")
    plot_df = df.tail(150)
    fig_k = go.Figure()
    # 主 K 線 (Category 軸解決空隙)
    fig_k.add_trace(go.Candlestick(
        x=plot_df.index.strftime('%Y-%m-%d'),
        open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
        increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
        name="台指日K"
    ))
    # 訊號：多(黃)、空(青)、平倉(白圓)
    for s, c, sym, ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -200), (-1, '#00F0FF', 'triangle-down', 'High', 200)]:
        sigs = plot_df[plot_df[sig_col] == s]
        if not sigs.empty:
            fig_k.add_trace(go.Scatter(
                x=sigs.index.strftime('%Y-%m-%d'), y=sigs[ref] + offset,
                mode='markers', marker=dict(symbol=sym, color=c, size=15), name=f'進場 {s}'
            ))
    # 平倉標記
    exit_sigs = plot_df[plot_df[sig_col] != 0]
    if not exit_sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=pd.to_datetime(exit_sigs['Exit_Date_10d']).dt.strftime('%Y-%m-%d'),
            y=exit_sigs['Exit_Price_10d'],
            mode='markers', marker=dict(symbol='circle', color='white', size=8), name='平倉點'
        ))

    fig_k.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
                        xaxis=dict(type='category', nticks=20), yaxis=dict(side="right"),
                        margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_k, use_container_width=True)

# 5. 明細
st.subheader("📋 交易明細")
st.dataframe(trades[['Close', 'Composite_Score', pnl_col, 'Cum_PnL']].sort_index(ascending=False).style.format("{:.0f}"))
st.sidebar.download_button("📥 下載 CSV", df.to_csv().encode('utf-8-sig'), "backtest.csv")
