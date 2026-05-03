import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# 指導原則：保留 1987 專業稅務/審計背景所需的精密感
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

# --- 診斷代碼定義 ---
# ERR-101: 找不到 CSV
# ERR-202: 欄位映射錯誤 (Signal 或 PnL 缺失)
# ERR-303: 日期區間內無交易資料
# ERR-404: 關鍵指標(如 ATR)缺失

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df, None
    return pd.DataFrame(), "ERR-101"

raw_df, init_err = load_data()

st.title("📈 台指期權量化回測系統 (專業視覺增強版)")

# -------------------------
# 1. 策略與期間設定
# -------------------------
st.sidebar.header("⚙️ 交易引擎與期間設定")

if init_err:
    st.error(f"🚨 系統錯誤代碼: {init_err} (找不到 CSV 檔案，請確認 GitHub Actions 已執行)")
    st.stop()

max_date = raw_df.index.max()
start_date = st.sidebar.date_input("回測開始日期", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("回測結束日期", value=max_date)

# 時區對齊處理
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

engine_choice = st.sidebar.selectbox("1. 選擇決策大腦", ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)"))
strategy_type = st.sidebar.radio("2. 選擇操作工具", ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)"))

st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態停損停利 (2R/1R)")
use_force_exit = st.sidebar.checkbox("開啟 7 天強制平倉")

# --- 映射邏輯 ---
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

# --- 錯誤診斷檢查 ---
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 系統錯誤代碼: ERR-202 (欄位缺失)")
    st.info(f"**診斷資訊**: 預期尋找 `{pnl_col}`，但該欄位不存在於目前的資料中。")
    st.stop()

# -------------------------
# 2. 績效與 MDD 計算
# -------------------------
trades = df[df[signal_col] != 0].copy()
if trades.empty:
    st.warning(f"⚠️ 診斷代碼: ERR-303 (此日期區間內無交易訊號)")
    st.stop()

trade_results = trades[pnl_col].dropna()
trades['Cumulative_PnL'] = trade_results.cumsum()
# 最大回撤公式: $$MDD = \min(PnL_{cumulative} - PnL_{peak})$$
running_max = trades['Cumulative_PnL'].cummax()
mdd = (trades['Cumulative_PnL'] - running_max).min()

st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("總交易次數", f"{len(trade_results)} 次")
c2.metric("策略勝率", f"{(len(trade_results[trade_results > 0]) / len(trade_results) * 100):.1f}%")
c3.metric("累積總損益", f"NT$ {trades['Cumulative_PnL'].iloc[-1]:,.0f}")
c4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
c5.metric("單筆期望值", f"NT$ {trade_results.mean():.0f}")

# -------------------------
# 3. 專業級 K 線視覺化 (修復版)
# -------------------------
st.subheader("📊 近期進出場點位標示 (專業交易終端模式)")
plot_df = df.tail(150) # 顯示最近 150 根，確保 K 棒寬度足夠

fig_k = go.Figure()

# 1. 主 K 線 (紅漲綠跌，增加線條對比)
fig_k.add_trace(go.Candlestick(
    x=plot_df.index,
    open=plot_df['Open'], high=plot_df['High'], low=plot_df['Low'], close=plot_df['Close'],
    increasing_line_color='#FF3333', decreasing_line_color='#00CC00',
    increasing_fillcolor='#FF3333', decreasing_fillcolor='#00CC00',
    name="台指K線"
))

# 2. 進出場標示 (偏移邏輯：買點在低點下 100 點，賣點在高點上 100 點)
for s, c, sym, pos_ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -100), (-1, '#00FFFF', 'triangle-down', 'High', 100)]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=sigs.index, y=sigs[pos_ref] + offset,
            mode='markers+text',
            marker=dict(symbol=sym, color=c, size=14, line=dict(width=1, color='white')),
            text=sigs[pos_col].astype(int).astype(str) + "口",
            textposition="bottom center" if s == 1 else "top center",
            name="進場訊號"
        ))

# 3. 佈局優化
fig_k.update_layout(
    height=600,
    template="plotly_dark",
    xaxis_rangeslider_visible=False,
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(
        type='category', # 強制使用類別型態，這會讓 K 棒寬度變真實且整齊，同時自動過濾週末空白
        tickangle=-45,
        nticks=20
    ),
    yaxis=dict(title="台指點數", side="right")
)

st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 操作建議與明細
# -------------------------
st.divider()
last_row = df.iloc[-1]
score = last_row.get('Composite_Score', 0)
support, resistance = df['Low'].tail(50).min(), df['High'].tail(50).max()

st.subheader("📋 交易明細紀錄")
st.dataframe(trades[['Close', 'Composite_Score', pnl_col, 'Cumulative_PnL']].sort_index(ascending=False).style.format("{:.0f}"))

# 側邊欄下載
st.sidebar.divider()
st.sidebar.download_button("📥 下載目前回測數據 CSV", df.to_csv().encode('utf-8-sig'), "backtest.csv")
