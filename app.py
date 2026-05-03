import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# 設定網頁標題與寬度 (保留原始設定)
st.set_page_config(page_title="台指選擇權全方位回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

raw_df = load_data()

st.title("📈 台指選擇權全方位回測系統 (含價差策略實證)")

if raw_df.empty:
    st.warning("⚠️ 尚未找到資料，請先執行 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 策略選擇區塊 (側邊欄 - 完整保留並新增期間選擇)
# -------------------------
st.sidebar.header("⚙️ 交易引擎設定")

# 【新增功能：回測期間選擇，不影響下方設定】
max_date = raw_df.index.max()
min_date_limit = max_date - timedelta(days=5*365)
start_date = st.sidebar.date_input("選擇回測開始日期", value=max_date - timedelta(days=365), min_value=min_date_limit.date(), max_value=max_date.date())
end_date = st.sidebar.date_input("選擇回測結束日期", value=max_date.date(), min_value=min_date_limit.date(), max_value=max_date.date())

# --- 修復時區 Bug：確保篩選資料時時區對齊 ---
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
if raw_df.index.tz is not None:
    ts_start = ts_start.tz_localize(raw_df.index.tz)
    ts_end = ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦 (邏輯核心)",
    ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)")
)

strategy_type = st.sidebar.radio(
    "2. 選擇操作策略",
    ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# 【新增功能：風險控管開關】
st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態停損停利 (2R/1R)")
use_force_exit = st.sidebar.checkbox("開啟 7 天強制平倉 (預設 10 天)")

# --- 動態欄位映射 (完全沿用原本邏輯並增加 RM 後綴) ---
if "3L-Strict" in engine_choice:
    prefix, pos_col, signal_col = '3L_Strict', 'Pos_3L_Strict', 'Signal_3L_Strict'
elif "3L-Relaxed" in engine_choice:
    prefix, pos_col, signal_col = '3L_Relaxed', 'Pos_3L_Relaxed', 'Signal_3L_Relaxed'
elif "MAD" in engine_choice:
    prefix, pos_col, signal_col = 'MAD', 'Pos_MAD', 'Signal_MAD'
else:
    prefix, pos_col, signal_col = 'Dir', 'Pos_Dir', 'Signal_Dir'

# 決定風控後綴
rm_suffix = "_RM" if (use_rm or use_force_exit) else ""

# 根據操作策略切換損益欄位 (保留原本名稱並對接工具名稱)
if "純微台期" in strategy_type:
    pnl_col = f"{prefix}_Micro{rm_suffix}_PnL_TWD"
    desc = "微台策略：無時間價值流失，單純追蹤日K趨勢。"
elif "賣方" in strategy_type:
    pnl_col = f"{prefix}_Seller{rm_suffix}_PnL_TWD"
    desc = "期貨+賣方收租：利用時間價值貼補成本。"
elif "純買方" in strategy_type:
    pnl_col = f"{prefix}_Buy{rm_suffix}_PnL_TWD"
    desc = "純買方策略：追求高槓桿爆發力，適合趨勢極其明確時。"
elif "價差策略" in strategy_type:
    pnl_col = f"{prefix}_Spread{rm_suffix}_PnL_TWD"
    desc = "價差策略：透過賣出遠端合約降低成本與 Theta 消耗，曲線較平穩。"
else:
    # 鐵蝴蝶維持獨立邏輯
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'
    desc = "中性策略：預期市場波動收斂。"

st.header(f"當前執行：{engine_choice} - {strategy_type}")
st.caption(desc)

# -------------------------
# 【新增區塊：即時診斷與操作建議 - 不動原本功能】
# -------------------------
st.divider()
st.subheader("🔍 即時診斷與目前操作建議")
if not df.empty:
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else last_row
    score = last_row.get('Composite_Score', 0)
    prev_score = prev_row.get('Composite_Score', 0)

    # 盤感診斷邏輯
    if score >= 0.66: status = "🔥 多頭持續 (強勁趨勢)"
    elif score > 0 and prev_score <= 0: status = "🚀 多頭開始 (初升段)"
    elif score > 0 and score < prev_score: status = "⚠️ 多頭勢歇 (高位震盪)"
    elif score <= -0.66: status = "❄️ 空頭持續 (強勁趨勢)"
    elif score < 0 and prev_score >= 0: status = "📉 空頭開始 (初跌段)"
    elif score < 0 and score > prev_score: status = "🩹 空頭勢歇 (跌勢趨緩)"
    elif score == 0 and prev_score != 0: status = "🧱 進入盤整 (動能消失)"
    else: status = "🔄 盤整持續"

    # 支撐壓力與口數
    support, resistance = df['Low'].tail(100).min(), df['High'].tail(100).max()
    suggested_pos = int(last_row.get(pos_col, 0)) if last_row.get(signal_col, 0) != 0 else 0

    d1, d2, d3 = st.columns(3)
    d1.metric("當前盤勢診斷", status)
    d2.metric("關鍵支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
    d3.metric("目前建議口數", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# -------------------------
# 2. 核心績效計算 (保留原本 5 欄顯示並加入 MDD)
# -------------------------
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 找不到對應欄位 (訊號: {signal_col}, 損益: {pnl_col})。")
    st.stop()

trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    sharpe = (ev / trade_results.std()) * np.sqrt(252) if trade_results.std() != 0 else 0
    trades['Cumulative_PnL'] = trades[pnl_col].cumsum()
    total_pnl = trades['Cumulative_PnL'].iloc[-1]
    
    # 【新增：MDD 計算】
    running_max = trades['Cumulative_PnL'].cummax()
    mdd = (trades['Cumulative_PnL'] - running_max).min()
else:
    win_rate = ev = sharpe = total_pnl = mdd = 0
    trades['Cumulative_PnL'] = 0

# 保留原本的 5 欄佈局
st.divider()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("總交易次數", f"{len(trade_results)} 次")
col2.metric("策略勝率", f"{win_rate:.2f}%")
col3.metric("單筆期望值", f"NT$ {ev:.0f}")
col4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}") # 將夏普換成更重要的 MDD，或保留原樣
col5.metric("累積總損益", f"NT$ {total_pnl:,.0f}")

# -------------------------
# 3. 繪製圖表 (保留原本繪圖風格)
# -------------------------
st.subheader("💰 累積損益曲線")
if len(trades) > 0:
    fig_pnl = go.Figure()
    line_color = 'rgba(50, 205, 50, 0.8)' if total_pnl > 0 else 'rgba(255, 69, 0, 0.8)'
    fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], mode='lines', fill='tozeroy', name='累積損益(TWD)', line=dict(color=line_color)))
    fig_pnl.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位標示")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="台指K線")])

# 繪製支撐壓力虛線
fig_k.add_hline(y=support, line_dash="dash", line_color="green", opacity=0.5)
fig_k.add_hline(y=resistance, line_dash="dash", line_color="red", opacity=0.5)

for s, c, name, sym in [(1, 'red', '多頭佈局', 'triangle-up'), (-1, 'green', '空頭佈局', 'triangle-down')]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(x=sigs.index, y=sigs['Entry_Price'], mode='markers+text', marker=dict(symbol=sym, color=c, size=14), name=name, text=sigs[pos_col].astype(int).astype(str) + " 組"))

fig_k.update_layout(height=550, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細 (保留原本格式化美化)
# -------------------------
st.subheader("📋 交易紀錄與多空實證明細")
display_cols = ['Close', 'YZ_Vol', 'Composite_Score', 'MAD_Value', signal_col, pos_col, pnl_col, 'Cumulative_PnL']
actual_cols = [c for c in display_cols if c in trades.columns]

if not trades.empty:
    st.dataframe(trades[actual_cols].sort_index(ascending=False).style.format({
        'Close': '{:.0f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', 'MAD_Value': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
    }))

# CSV 下載按鈕
csv = df.to_csv().encode('utf-8-sig')
st.download_button(label="📥 下載目前回測數據 CSV", data=csv, file_name='txf_backtest.csv', mime='text/csv')
