import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime, timedelta

# 設定網頁標題與寬度
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

# --- 錯誤診斷系統 ---
ERROR_MAP = {
    "ERR-101": "檔案缺失 (data/txf_options_backtest.csv)",
    "ERR-202": "欄位對接失敗 (Signal 或 PnL 欄位未產出)",
    "ERR-303": "日期範圍無資料 (請檢查回測期間設定)",
    "ERR-404": "資料索引格式錯誤 (時區不相容)"
}

@st.cache_data(ttl=300)
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        # 讀取時確保日期格式正確
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df, None
    return pd.DataFrame(), "ERR-101"

raw_df, init_err = load_data()

st.title("📈 台指期權量化回測系統 (專業視覺增強版)")

# -------------------------
# 1. 策略與期間設定 (側邊欄)
# -------------------------
st.sidebar.header("⚙️ 引擎與期間")
if init_err:
    st.error(f"🚨 系統錯誤: {init_err} ({ERROR_MAP[init_err]})")
    st.stop()

# 取得資料範圍進行連動
max_date = raw_df.index.max()
start_date = st.sidebar.date_input("回測開始日期", value=max_date - timedelta(days=365))
end_date = st.sidebar.date_input("回測結束日期", value=max_date)

# --- 修復時區與切片問題 ---
ts_start = pd.Timestamp(start_date)
ts_end = pd.Timestamp(end_date) + pd.Timedelta(hours=23, minutes=59)

# 針對 yfinance 常見時區進行自動對齊
if raw_df.index.tz is not None:
    ts_start = ts_start.tz_localize(raw_df.index.tz)
    ts_end = ts_end.tz_localize(raw_df.index.tz)

# 回測與 K 棒時間軸完全連動
df = raw_df.loc[ts_start:ts_end].copy()

if df.empty:
    st.error(f"🚨 系統錯誤: ERR-303 ({ERROR_MAP['ERR-303']})")
    st.stop()

# 策略選擇邏輯
engine_choice = st.sidebar.selectbox("1. 選擇決策大腦", ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型"))
strategy_type = st.sidebar.radio("2. 選擇操作工具", ("純微台期 (10元/點)", "期貨 + 選擇權賣方 (收租型)", "純買方 (Long Call/Put)", "價差策略 (Bull/Bear Spread)", "中性盤整 (鐵蝴蝶)"))

# 風控插件設定
st.sidebar.header("🛡️ 風險控管插件")
use_rm = st.sidebar.checkbox("開啟 ATR 動態風控與 7 天平倉")

# --- 映射邏輯 ---
brain_map = {"法人 3L-Strict (0.33門檻)": "3L_Strict", "法人 3L-Relaxed (0門檻)": "3L_Relaxed", "MAD 均線距離策略": "MAD", "基礎指標模型": "Dir"}
tool_map = {"純微台期 (10元/點)": "Micro", "期貨 + 選擇權賣方 (收租型)": "Seller", "純買方 (Long Call/Put)": "Buy", "價差策略 (Bull/Bear Spread)": "Spread"}

b_prefix = brain_map.get(engine_choice, "Dir")
t_prefix = tool_map.get(strategy_type, "Micro")
rm_suffix = "_RM" if use_rm else ""

pnl_col = f"{b_prefix}_{t_prefix}{rm_suffix}_PnL_TWD"
signal_col = f"Signal_{b_prefix}"
pos_col = f"Pos_{b_prefix}"

# --- 欄位診斷代碼 ---
if pnl_col not in df.columns or signal_col not in df.columns:
    st.error(f"🚨 系統錯誤: ERR-202 (欄位缺失)")
    st.info(f"**診斷資訊**: 找不到損益欄位 `{pnl_col}` 或訊號欄位 `{signal_col}`。")
    st.caption("請確認 GitHub Actions 已完成且產出了對應的 RM 風控欄位。")
    st.stop()

# -------------------------
# 2. 核心績效計算 (包含 MDD)
# -------------------------
trades = df[df[signal_col] != 0].copy()
if not trades.empty:
    trades['Cum_PnL'] = trades[pnl_col].cumsum()
    running_max = trades['Cum_PnL'].cummax()
    mdd = (trades['Cum_PnL'] - running_max).min()
    
    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總交易次數", f"{len(trades)} 次")
    c2.metric("策略勝率", f"{(len(trades[trades[pnl_col]>0])/len(trades)*100):.1f}%")
    c3.metric("累積總損益", f"NT$ {trades['Cum_PnL'].iloc[-1]:,.0f}")
    c4.metric("最大回撤 (MDD)", f"NT$ {mdd:,.0f}")
    c5.metric("單筆期望值", f"NT$ {trades[pnl_col].mean():.0f}")

# -------------------------
# 3. 專業級 K 線視覺化 (同步日期軸)
# -------------------------
st.subheader("📊 回測期間 K 線標示 (顯示年月日軸)")

# 為了讓 K 棒保持真實感，過濾資料量避免圖表過載
plot_df = df.tail(150) if len(df) > 150 else df 

fig_k = go.Figure()

# 主 K 線：優化飽滿度與專業紅綠配色
fig_k.add_trace(go.Candlestick(
    x=plot_df.index,
    open=plot_df['Open'], high=plot_df['High'], 
    low=plot_df['Low'], close=plot_df['Close'],
    increasing_line_color='#FF3232', decreasing_line_color='#32FF32',
    increasing_fillcolor='#FF3232', decreasing_fillcolor='#32FF32',
    name="台指1H K線"
))

# 訊號標示：偏移量避開 K 棒主體
for s, c, sym, ref, offset in [(1, '#FFD700', 'triangle-up', 'Low', -100), (-1, '#00F0FF', 'triangle-down', 'High', 100)]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=sigs.index, 
            y=sigs[ref] + offset,
            mode='markers+text',
            marker=dict(symbol=sym, color=c, size=15),
            text=sigs[pos_col].astype(int).astype(str) + "口",
            textposition="bottom center" if s == 1 else "top center",
            name="進場訊號"
        ))

# 佈局優化：解決消失問題、格式化年月日
fig_k.update_layout(
    height=600, template="plotly_dark",
    xaxis_rangeslider_visible=False,
    xaxis=dict(
        type='date',
        tickformat='%Y-%m-%d',  # 僅顯示年月日
        rangebreaks=[dict(bounds=["sat", "mon"])], # 隱藏週末空白
        gridcolor='rgba(255,255,255,0.05)'
    ),
    yaxis=dict(side="right", gridcolor='rgba(255,255,255,0.05)'),
    margin=dict(l=10, r=10, t=10, b=10)
)
st.plotly_chart(fig_k, use_container_width=True)

# 4. 下載按鈕 (側邊欄)
st.sidebar.divider()
st.sidebar.download_button("📥 下載目前回測 CSV", df.to_csv().encode('utf-8-sig'), "backtest_data.csv")
