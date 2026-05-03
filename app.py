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

st.title("📈 台指期權量化回測與即時診斷系統")

if raw_df.empty:
    st.warning("⚠️ 尚未找到資料，請先在 GitHub 執行最新版 `update_data.py`。")
    st.stop()

# -------------------------
# 1. 側邊欄設定
# -------------------------
st.sidebar.header("⚙️ 交易引擎與期間設定")

# 新增：回測期間選擇 (最多5年)
max_date = raw_df.index.max()
min_date_limit = max_date - timedelta(days=5*365)
start_date = st.sidebar.date_input("選擇回測開始日期", value=max_date - timedelta(days=365), min_value=min_date_limit.date(), max_value=max_date.date())
end_date = st.sidebar.date_input("選擇回測結束日期", value=max_date.date(), min_value=min_date_limit.date(), max_value=max_date.date())

# 根據日期篩選資料
df = raw_df.loc[start_date:end_date].copy()

engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦",
    ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型")
)

strategy_type = st.sidebar.radio(
    "2. 選擇操作工具",
    ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)")
)

st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態停損停利 (2R/1R)")
use_force_exit = st.sidebar.checkbox("開啟 7 天強制平倉")

# --- 邏輯映射 ---
if "3L-Strict" in engine_choice: brain_prefix = '3L_Strict'
elif "3L-Relaxed" in engine_choice: brain_prefix = '3L_Relaxed'
elif "MAD" in engine_choice: brain_prefix = 'MAD'
else: brain_prefix = 'Dir'

rm_suffix = "_RM" if (use_rm or use_force_exit) else ""

if "純微台期" in strategy_type: pnl_col = f'{brain_prefix}_Micro{rm_suffix}_PnL_TWD'
elif "賣方" in strategy_type: pnl_col = f'{brain_prefix}_Seller{rm_suffix}_PnL_TWD'
elif "純買方" in strategy_type: pnl_col = f'{brain_prefix}_Buy{rm_suffix}_PnL_TWD'
elif "價差策略" in strategy_type: pnl_col = f'{brain_prefix}_Spread{rm_suffix}_PnL_TWD'
else: signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

signal_col = f'Signal_{brain_prefix}' if "中性" not in strategy_type else 'Signal_IB'
pos_col = f'Pos_{brain_prefix}' if "中性" not in strategy_type else 'Pos_IB'

# -------------------------
# 2. 即時診斷與操作建議 (基於最新數據)
# -------------------------
st.header("🔍 即時監控與操作建議")
last_row = df.iloc[-1]
prev_row = df.iloc[-2]
score = last_row.get('Composite_Score', 0)
close_price = last_row['Close']

# A. 盤勢診斷邏輯
if score >= 0.66: status = "🔥 多頭持續 (強勁趨勢)"
elif score > 0 and prev_row.get('Composite_Score', 0) <= 0: status = "🚀 多頭開始 (初升段)"
elif score > 0 and score < prev_row.get('Composite_Score', 0): status = "⚠️ 多頭勢歇 (高位震盪)"
elif score <= -0.66: status = "❄️ 空頭持續 (強勁趨勢)"
elif score < 0 and prev_row.get('Composite_Score', 0) >= 0: status = "📉 空頭開始 (初跌段)"
elif score < 0 and score > prev_row.get('Composite_Score', 0): status = "🩹 空頭勢歇 (超跌反彈)"
elif score == 0 and prev_row.get('Composite_Score', 0) != 0: status = "🧱 進入盤整 (動能消失)"
else: status = "🔄 盤整持續 (橫盤)"

# B. 壓力與支撐 (取最近 20 日/100根K線高低點)
support = df['Low'].tail(100).min()
resistance = df['High'].tail(100).max()

# C. 操作建議口數
suggested_pos = int(last_row.get(pos_col, 1)) if last_row.get(signal_col, 0) != 0 else 0

diag_col1, diag_col2, diag_col3 = st.columns(3)
diag_col1.metric("當前盤感診斷", status)
diag_col2.metric("關鍵支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
diag_col3.metric(f"建議操作口數 ({strategy_type})", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# -------------------------
# 3. 核心績效與 MDD 計算
# -------------------------
trades = df[df[signal_col] != 0].copy()
if pnl_col in trades.columns:
    trade_results = trades[pnl_col].dropna()
    trades['Cumulative_PnL'] = trade_results.cumsum()
    
    # MDD 計算
    cum_pnl = trades['Cumulative_PnL']
    running_max = cum_pnl.cummax()
    drawdown = cum_pnl - running_max
    mdd = drawdown.min()
    
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results) * 100) if len(trade_results) > 0 else 0
    total_pnl = trades['Cumulative_PnL'].iloc[-1] if not trades.empty else 0
else:
    st.error(f"🚨 找不到欄位 {pnl_col}")
    st.stop()

st.divider()
perf_col1, perf_col2, perf_col3, perf_col4 = st.columns(4)
perf_col1.metric("累積總損益", f"NT$ {total_pnl:,.0f}")
perf_col2.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}", delta_color="inverse")
perf_col3.metric("策略勝率", f"{win_rate:.2f}%")
perf_col4.metric("交易次數", f"{len(trade_results)} 次")

# -------------------------
# 4. 繪製圖表
# -------------------------
st.subheader("💰 權益曲線與 MDD 區域")
fig_pnl = go.Figure()
fig_pnl.add_trace(go.Scatter(x=trades.index, y=trades['Cumulative_PnL'], name="累積損益", fill='tozeroy', line=dict(color='cyan')))
fig_pnl.update_layout(height=400, template="plotly_dark")
st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 進出場點位標示 (近期走勢)")
plot_df = df.tail(200)
fig_k = go.Figure(data=[go.Candlestick(x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'], name="台指K線")])
# 畫支撐壓力線
fig_k.add_hline(y=support, line_dash="dash", line_color="green", annotation_text="近期支撐")
fig_k.add_hline(y=resistance, line_dash="dash", line_color="red", annotation_text="近期壓力")

for s, c, sym in [(1, 'red', 'triangle-up'), (-1, 'green', 'triangle-down')]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(x=sigs.index, y=sigs['Entry_Price'], mode='markers', marker=dict(symbol=sym, color=c, size=12), name="進場訊號"))

fig_k.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark")
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 5. 明細與下載
# -------------------------
st.subheader("📋 交易明細清單")
st.dataframe(trades[['Close', 'Composite_Score', pnl_col, 'Cumulative_PnL']].sort_index(ascending=False).style.format("{:.0f}"))

csv = df.to_csv().encode('utf-8-sig')
st.download_button(label="📥 下載回測數據", data=csv, file_name=f'backtest_{engine_choice}.csv', mime='text/csv')
