import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# --- [最高指導原則] 嚴格保留框架與功能，優化視覺真實感 ---
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

# 系統診斷代碼定義
ERROR_MAP = {
    "ERR-101": "資料庫檔案缺失 (CSV not found)",
    "ERR-202": "策略欄位映射失敗 (Column missing - 請檢查 update_data.py)",
    "ERR-303": "目前日期區間內無任何交易訊號",
    "ERR-404": "時區對齊或資料索引格式異常"
}

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
# 1. 側邊欄設定 (完整功能框架)
# -------------------------
st.sidebar.header("⚙️ 交易引擎與期間設定")

if init_err:
    st.error(f"🚨 系統錯誤: {init_err} ({ERROR_MAP[init_err]})")
    st.stop()

# 回測期間選擇 (最多5年)
max_date = raw_df.index.max()
min_date_limit = max_date - timedelta(days=5*365)
start_date = st.sidebar.date_input("回測開始日期", value=max_date - timedelta(days=365), min_value=min_date_limit.date(), max_value=max_date.date())
end_date = st.sidebar.date_input("回測結束日期", value=max_date.date(), min_value=min_date_limit.date(), max_value=max_date.date())

# 時區自動對齊處理
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)
if raw_df.index.tz is not None:
    ts_start, ts_end = ts_start.tz_localize(raw_df.index.tz), ts_end.tz_localize(raw_df.index.tz)

df = raw_df.loc[ts_start:ts_end].copy()

# 決策大腦映射
engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦 (邏輯核心)",
    ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)")
)

strategy_type = st.sidebar.radio(
    "2. 選擇操作策略",
    ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶 Iron Butterfly)")
)

# 風險控管開關
st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態風控與 7 天平倉", value=True)

# 映射邏輯 (對齊後端生成名稱)
brain_map = {"法人 3L-Strict (0.33門檻)": "3L_Strict", "法人 3L-Relaxed (0門檻)": "3L_Relaxed", "MAD 均線距離策略": "MAD", "基礎指標模型 (MACD/ATR)": "Dir"}
tool_map = {"純微台期 (10元/點)": "Micro", "期貨 + 選擇權賣方 (收租型)": "Seller", "純買方 (Long Call/Put)": "Buy", "價差策略 (Bull/Bear Spread)": "Spread"}

b_prefix = brain_map.get(engine_choice, "Dir")
t_prefix = tool_map.get(strategy_type, "Micro")
rm_suffix = "_RM" if use_rm else ""

pnl_col = f"{b_prefix}_{t_prefix}{rm_suffix}_PnL_TWD"
signal_col = f"Signal_{b_prefix}"
pos_col = f"Pos_{b_prefix}"

if "鐵蝴蝶" in strategy_type:
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'

# 下載按鈕
st.sidebar.divider()
st.sidebar.download_button("📥 下載目前回測 CSV", df.to_csv().encode('utf-8-sig'), "backtest_export.csv")

# -------------------------
# 2. 即時診斷與操作建議
# -------------------------
st.header("🔍 即時診斷與操作建議")
if not df.empty:
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) > 1 else last_row
    score = last_row.get('Composite_Score', 0)
    prev_score = prev_row.get('Composite_Score', 0)

    # 盤勢狀態診斷邏輯
    if score >= 0.66: status = "🔥 多頭持續 (強勁趨勢)"
    elif score > 0 and prev_score <= 0: status = "🚀 多頭開始 (初升發動)"
    elif score > 0 and score < prev_score: status = "⚠️ 多頭勢歇 (動能減弱)"
    elif score <= -0.66: status = "❄️ 空頭持續 (強勁趨勢)"
    elif score < 0 and prev_score >= 0: status = "📉 空頭開始 (起跌確認)"
    elif score < 0 and score > prev_score: status = "🩹 空頭勢歇 (跌勢趨緩)"
    else: status = "🔄 盤整持續"

    support, resistance = df['Low'].tail(100).min(), df['High'].tail(100).max()
    suggested_pos = int(last_row.get(pos_col, 0)) if last_row.get(signal_col, 0) != 0 else 0

    d1, d2, d3 = st.columns(3)
    d1.metric("當前盤勢診斷", status)
    d2.metric("關鍵支撐 / 壓力", f"{support:.0f} / {resistance:.0f}")
    d3.metric("目前建議口數", f"{suggested_pos} 口" if suggested_pos > 0 else "觀望")

# 欄位診斷代碼 (如有缺失會在此報錯)
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 系統診斷代碼: ERR-202 (欄位缺失)")
    st.info(f"**診斷資訊**: 找不到欄位 `{pnl_col}`。請確認後端 update_data.py 是否產出該欄位。")
    st.stop()

# -------------------------
# 3. 核心績效計算 (保留 5 欄框架)
# -------------------------
trades = df[df[signal_col] != 0].copy()
if trades.empty:
    st.warning(f"⚠️ 診斷代碼: ERR-303 (此區間無訊號)")
    st.stop()

trade_results = trades[pnl_col].dropna()
trades['Cumulative_PnL'] = trade_results.cumsum()

# 夏普值 (Sharpe Ratio)
sharpe = (trade_results.mean() / trade_results.std() * np.sqrt(252)) if trade_results.std() != 0 else 0
# 最大回撤 (MDD)
running_max = trades['Cumulative_PnL'].cummax()
mdd = (trades['Cumulative_PnL'] - running_max).min()

st.divider()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("總交易次數", f"{len(trade_results)} 次")
c2.metric("策略勝率", f"{(len(trade_results[trade_results > 0]) / len(trade_results) * 100):.1f}%")
c3.metric("策略夏普值", f"{sharpe:.2f}")
c4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
c5.metric("累積總損益", f"NT$ {trades['Cumulative_PnL'].iloc[-1]:,.0f}")

# -------------------------
# 4. 圖表顯示區 (修正順序：損益在上，K棒在下)
# -------------------------

# (1) 累積損益曲線
st.subheader("💰 累積損益曲線 (Equity Curve)")
fig_pnl = go.Figure(data=[go.Scatter(
    x=trades.index, y=trades['Cumulative_PnL'], 
    mode='lines', fill='tozeroy', 
    line=dict(color='rgba(50, 205, 50, 0.8)', width=2)
)])
fig_pnl.update_layout(height=350, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_pnl, use_container_width=True)

# (2) 專業 K 線圖 (視覺優化版)
st.subheader("📊 走勢標示 (專業交易終端模式)")
# 確保資料量適合顯示 (若期間太長則顯示最近 200 根)
plot_df = df.tail(200) if len(df) > 200 else df

fig_k = go.Figure()
# 主 K 線：專業紅綠配色
fig_k.add_trace(go.Candlestick(
    x=plot_df.index,
    open=plot_df['Open'], high=plot_df['High'], 
    low=plot_df['Low'], close=plot_df['Close'],
    increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
    increasing_fillcolor='#FF3232', decreasing_fillcolor='#32FF32',
    name="台指1H K線"
))

# 訊號標示：增加位移避免與 K 棒重疊
for s, c, sym, ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -120), (-1, '#00F0FF', 'triangle-down', 'High', 120)]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=sigs.index, y=sigs[ref] + offset,
            mode='markers+text',
            marker=dict(symbol=sym, color=c, size=15, line=dict(width=1, color='white')),
            text=sigs[pos_col].astype(int).astype(str) + "口",
            textposition="bottom center" if s == 1 else "top center",
            name="進場訊號"
        ))

fig_k.update_layout(
    height=600, template="plotly_dark", xaxis_rangeslider_visible=False,
    xaxis=dict(
        type='date',
        tickformat='%Y-%m-%d',
        rangebreaks=[dict(bounds=["sat", "mon"])] # 隱藏週末空白
    ),
    yaxis=dict(side="right", gridcolor='rgba(255,255,255,0.05)'),
    margin=dict(l=10, r=10, t=30, b=10)
)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 5. 交易明細 (美化格式)
# -------------------------
st.subheader("📋 交易紀錄與多空實證明細")
st.dataframe(trades[['Close', 'YZ_Vol', 'Composite_Score', pnl_col, 'Cumulative_PnL']].sort_index(ascending=False).style.format({
    'Close': '{:.0f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
}))
