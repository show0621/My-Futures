import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# 設定網頁標題與寬度
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

raw_df = load_data()

st.title("📈 台指期貨與選擇權全方位回測系統 (法人級波段版)")

if raw_df.empty:
    st.warning("⚠️ 尚未找到資料，請先在 GitHub 執行最新版 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 策略與期間設定 (側邊欄)
# -------------------------
st.sidebar.header("⚙️ 交易引擎與期間設定")

max_date = raw_df.index.max()
min_date_limit = max_date - timedelta(days=5*365)
start_date = st.sidebar.date_input("選擇回測開始日期", value=max_date - timedelta(days=365), min_value=min_date_limit.date(), max_value=max_date.date())
end_date = st.sidebar.date_input("選擇回測結束日期", value=max_date.date(), min_value=min_date_limit.date(), max_value=max_date.date())

# 時區處理
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

engine_choice = st.sidebar.selectbox("1. 選擇決策大腦", ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)"))
strategy_type = st.sidebar.radio("2. 選擇操作工具", ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶 Iron Butterfly)"))

st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態停損停利 (2R/1R)")
use_force_exit = st.sidebar.checkbox("開啟 7 天強制平倉 (預設 10 天)")

# --- 核心邏輯：動態欄位映射 ---
if "3L-Strict" in engine_choice: brain_prefix = '3L_Strict'
elif "3L-Relaxed" in engine_choice: brain_prefix = '3L_Relaxed'
elif "MAD" in engine_choice: brain_prefix = 'MAD'
else: brain_prefix = 'Dir'

signal_col, pos_col = f'Signal_{brain_prefix}', f'Pos_{brain_prefix}'
rm_suffix = "_RM" if (use_rm or use_force_exit) else ""

if "純微台期" in strategy_type: pnl_col = f'{brain_prefix}_Micro{rm_suffix}_PnL_TWD'
elif "賣方" in strategy_type: pnl_col = f'{brain_prefix}_Seller{rm_suffix}_PnL_TWD'
elif "純買方" in strategy_type: pnl_col = f'{brain_prefix}_Buy{rm_suffix}_PnL_TWD'
elif "價差策略" in strategy_type: pnl_col = f'{brain_prefix}_Spread{rm_suffix}_PnL_TWD'
else: signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# 下載按鈕 (側邊欄確保永遠存在)
st.sidebar.divider()
st.sidebar.download_button(label="📥 下載目前回測數據 CSV", data=df.to_csv().encode('utf-8-sig'), file_name='txf_backtest.csv', mime='text/csv')

# -------------------------
# 2. 即時診斷與操作建議
# -------------------------
st.header("🔍 即時診斷與目前操作建議")
if not df.empty:
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else last_row
    score, prev_score = last_row.get('Composite_Score', 0), prev_row.get('Composite_Score', 0)

    if score >= 0.66: diag = "🔥 多頭持續 (強勁趨勢)"
    elif score > 0 and prev_score <= 0: diag = "🚀 多頭開始 (趨勢發動)"
    elif score > 0 and score < prev_score: diag = "⚠️ 多頭勢歇 (動能減弱)"
    elif score <= -0.66: diag = "❄️ 空頭持續 (強勁趨勢)"
    elif score < 0 and prev_score >= 0: diag = "📉 空頭開始 (起跌確認)"
    elif score < 0 and score > prev_score: diag = "🩹 空頭勢歇 (跌勢趨緩)"
    elif score == 0 and prev_score != 0: diag = "🧱 進入盤整 (動能消失)"
    else: diag = "🔄 盤整持續"

    support, resistance = df['Low'].tail(100).min(), df['High'].tail(100).max()
    suggested_pos = int(last_row.get(pos_col, 0)) if last_row.get(signal_col, 0) != 0 else 0

    d1, d2, d3 = st.columns(3)
    d1.metric("當前盤勢診斷", diag)
    d2.metric("關鍵支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
    d3.metric("目前建議口數", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# --- 防呆檢查 ---
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 找不到對應欄位 (訊號: {signal_col}, 損益: {pnl_col})。請先手動觸發 GitHub 執行 update_data.py。")
    st.stop()

# -------------------------
# 3. 核心績效計算 (含 MDD)
# -------------------------
trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    sharpe = (ev / trade_results.std()) * np.sqrt(252) if trade_results.std() != 0 else 0
    trades['Cumulative_PnL'] = trades[pnl_col].cumsum()
    # MDD: 累積損益 - 歷史高點
    running_max = trades['Cumulative_PnL'].cummax()
    mdd = (trades['Cumulative_PnL'] - running_max).min()
    total_pnl = trades['Cumulative_PnL'].iloc[-1]
else:
    win_rate = ev = sharpe = total_pnl = mdd = 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("總交易次數", f"{len(trade_results)} 次")
col2.metric("策略勝率", f"{win_rate:.2f}%")
col3.metric("策略夏普值", f"{sharpe:.2f}")
col4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
col5.metric("累積總損益", f"NT$ {total_pnl:,.0f}")

# -------------------------
# 4. 繪製圖表
# -------------------------
st.subheader(f"💰 累積損益曲線 ({start_date} ~ {end_date})")
if len(trades) > 0:
    fig_pnl = go.Figure()
    line_color = 'rgba(50, 205, 50, 0.8)' if total_pnl > 0 else 'rgba(255, 69, 0, 0.8)'
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], mode='lines', fill='tozeroy', line=dict(color=line_color)))
    fig_pnl.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位標示 (含支撐壓力)")
plot_df = df.tail(300)
if not plot_df.empty:
    fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="台指K線")])
    fig_k.add_hline(y=support, line_dash="dash", line_color="green", annotation_text="支撐")
    fig_k.add_hline(y=resistance, line_dash="dash", line_color="red", annotation_text="壓力")
    for s, c, sym in [(1, 'red', 'triangle-up'), (-1, 'green', 'triangle-down')]:
        sigs = plot_df[plot_df[signal_col] == s]
        if not sigs.empty:
            fig_k.add_trace(go.Scatter(x=sigs.index, y=sigs['Entry_Price'], mode='markers+text', marker=dict(symbol=sym, color=c, size=14), text=sigs[pos_col].astype(int).astype(str) + " 組"))
    fig_k.update_layout(height=550, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 5. 交易明細紀錄
# -------------------------
st.subheader("📋 交易紀錄與多空實證明細")
display_cols = ['Close', 'YZ_Vol', 'Composite_Score', 'MAD_Value', signal_col, pos_col, pnl_col, 'Cumulative_PnL']
actual_cols = [c for c in display_cols if c in trades.columns]
if not trades.empty:
    st.dataframe(trades[actual_cols].sort_index(ascending=False).style.format("{:.0f}"))
