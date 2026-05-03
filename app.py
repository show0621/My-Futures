import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# 設定網頁標題與寬度
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

# --- [新增] 錯誤診斷代碼對照表 ---
ERROR_MAP = {
    "ERR-COL-SIG": "找不到對應的大腦訊號欄位",
    "ERR-COL-PNL": "找不到對應的損益計算欄位 (可能 update_data.py 未更新 RM 邏輯)",
    "ERR-DATA-EMPTY": "選擇的日期區間內沒有回測資料",
    "ERR-FILE-MISSING": "找不到後端生成的 CSV 檔案",
    "ERR-TZ-MISMATCH": "系統時區對齊發生異常"
}

@st.cache_data(ttl=600)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df, None
    return pd.DataFrame(), "ERR-FILE-MISSING"

raw_df, init_err = load_data()

st.title("📈 台指期權量化回測系統 (專業視覺增強版)")

# 初始檔案檢查
if init_err:
    st.error(f"🚨 系統診斷代碼: {init_err} ({ERROR_MAP[init_err]})")
    st.stop()

# -------------------------
# 1. 策略選擇區塊 (側邊欄)
# -------------------------
st.sidebar.header("⚙️ 交易引擎與期間設定")

max_date = raw_df.index.max()
start_date = st.sidebar.date_input("回測開始日期", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("回測結束日期", value=max_date)

# 時區對齊處理
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

if df.empty:
    st.error(f"🚨 系統診斷代碼: ERR-DATA-EMPTY ({ERROR_MAP['ERR-DATA-EMPTY']})")
    st.stop()

engine_choice = st.sidebar.selectbox("1. 選擇決策大腦", ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)"))
strategy_type = st.sidebar.radio("2. 選擇操作工具", ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)"))

st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態停損停利 (2R/1R)")
use_force_exit = st.sidebar.checkbox("開啟 7 天強制平倉")

# --- 核心邏輯映射 ---
if "3L-Strict" in engine_choice: brain_prefix = '3L_Strict'
elif "3L-Relaxed" in engine_choice: brain_prefix = '3L_Relaxed'
elif "MAD" in engine_choice: brain_prefix = 'MAD'
else: brain_prefix = 'Dir'

signal_col, pos_col = f'Signal_{brain_prefix}', f'Pos_{brain_prefix}'
rm_suffix = "_RM" if (use_rm or use_force_exit) else ""

if "純微台期" in strategy_type: pnl_col = f'{brain_prefix}_Micro{rm_suffix}_PnL_TWD'
elif "賣方" in strategy_type: pnl_col = f'{brain_prefix}_Seller{rm_suffix}_PnL_TWD'
elif "買方" in strategy_type: pnl_col = f'{brain_prefix}_Buy{rm_suffix}_PnL_TWD'
elif "價差策略" in strategy_type: pnl_col = f'{brain_prefix}_Spread{rm_suffix}_PnL_TWD'
else: signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# 下載按鈕
st.sidebar.divider()
st.sidebar.download_button(label="📥 下載回測 CSV", data=df.to_csv().encode('utf-8-sig'), file_name='backtest_export.csv')

# --- [新增] 欄位診斷系統 ---
current_error = None
if signal_col not in df.columns: current_error = "ERR-COL-SIG"
elif pnl_col not in df.columns: current_error = "ERR-COL-PNL"

if current_error:
    st.error(f"🚨 系統診斷代碼: {current_error}")
    st.info(f"**詳細原因**: {ERROR_MAP[current_error]}")
    st.caption(f"缺少的欄位預期名稱: `{pnl_col}`")
    st.stop()

# -------------------------
# 2. 即時診斷與操作建議
# -------------------------
st.header("🔍 即時診斷與操作建議")
last_row = df.iloc[-1]
score = last_row.get('Composite_Score', 0)
support, resistance = df['Low'].tail(50).min(), df['High'].tail(50).max()
suggested_pos = int(last_row.get(pos_col, 0)) if last_row.get(signal_col, 0) != 0 else 0

diag_col1, diag_col2, diag_col3 = st.columns(3)
diag_col1.metric("當前盤勢診斷", "🔥 強勢多頭" if score > 0.6 else "🔄 盤整震盪" if abs(score) < 0.3 else "❄️ 強勢空頭")
diag_col2.metric("關鍵支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
diag_col3.metric("建議操作口數", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# -------------------------
# 3. 核心績效與 MDD
# -------------------------
trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()
trades['Cumulative_PnL'] = trade_results.cumsum()
mdd = (trades['Cumulative_PnL'] - trades['Cumulative_PnL'].cummax()).min()

st.divider()
perf_col1, perf_col2, perf_col3, perf_col4, perf_col5 = st.columns(5)
perf_col1.metric("總交易次數", f"{len(trade_results)} 次")
perf_col2.metric("策略勝率", f"{(len(trade_results[trade_results > 0]) / len(trade_results) * 100):.1f}%")
perf_col3.metric("累積總損益", f"NT$ {trades['Cumulative_PnL'].iloc[-1]:,.0f}")
perf_col4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
perf_col5.metric("單筆期望值", f"NT$ {trade_results.mean():.0f}")

# -------------------------
# 4. 專業級 K 線視覺化 (改良區)
# -------------------------
st.subheader("📊 進出場點位標示 (專業交易終端風)")
plot_df = df.tail(150) # 縮小範圍增加清晰度

fig_k = go.Figure(data=[go.Candlestick(
    x=plot_df.index,
    open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
    increasing_line_color='#FF3333', decreasing_line_color='#00AA00', # 台股標準色
    increasing_fillcolor='#FF3333', decreasing_fillcolor='#00AA00',
    line_width=1, name="台指K線"
)])

# 繪製支撐壓力
fig_k.add_hline(y=support, line_dash="dash", line_color="#27AE60", opacity=0.6, annotation_text="支撐")
fig_k.add_hline(y=resistance, line_dash="dash", line_color="#E74C3C", opacity=0.6, annotation_text="壓力")

# 優化進場標記 (偏移顯示避免遮擋)
for s, c, sym, offset_dir in [(1, '#FFCC00', 'triangle-up', -1), (-1, '#00FFFF', 'triangle-down', 1)]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        # offset 計算：在高低點外側 0.5% 的位置
        y_pos = sigs['Low'] * (1 + 0.005 * offset_dir) if s == 1 else sigs['High'] * (1 + 0.005 * offset_dir)
        fig_k.add_trace(go.Scatter(
            x=sigs.index, y=y_pos, mode='markers+text',
            marker=dict(symbol=sym, color=c, size=12, line=dict(width=1, color='white')),
            name="進場訊號", text=sigs[pos_col].astype(int).astype(str) + "口",
            textposition="bottom center" if s == 1 else "top center"
        ))

fig_k.update_layout(
    height=650, xaxis_rangeslider_visible=False,
    template="plotly_dark", # 深色背景更具專業感
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(
        type='date',
        rangebreaks=[
            dict(bounds=["sat", "mon"]), # 隱藏週末
            dict(bounds=[14, 8], pattern="hour"), # 隱藏非交易時段 (視台指盤後調整)
        ]
    )
)
st.plotly_chart(fig_k, use_container_width=True)

# 5. 明細 (保留原本功能)
st.subheader("📋 交易明細紀錄")
st.dataframe(trades[['Close', 'YZ_Vol', 'Composite_Score', pnl_col, 'Cumulative_PnL']].sort_index(ascending=False).style.format("{:.0f}"))
