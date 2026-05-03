import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

# 設定網頁標題與寬度
st.set_page_config(page_title="台指全方位量化回測系統", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        # 讀取 CSV 並將索引設定為時間格式
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

df = load_data()

st.title("📈 台指期貨與選擇權全方位回測系統 (法人級波段版)")

# 基礎資料檢查
if df.empty:
    st.warning("⚠️ 尚未找到資料，請先在 GitHub 執行最新版 `update_data.py` 並確認 Actions 執行成功。")
    st.stop()

# -------------------------
# 1. 策略選擇區塊 (側邊欄)
# -------------------------
st.sidebar.header("⚙️ 交易引擎設定")

engine_choice = st.sidebar.selectbox(
    "1. 選擇決策大腦 (趨勢邏輯)",
    ("法人 3L-Strict (0.33門檻)", "法人 3L-Relaxed (0門檻)", "MAD 均線距離策略", "基礎指標模型 (MACD/ATR)")
)

strategy_type = st.sidebar.radio(
    "2. 選擇操作工具 (損益計算模型)",
    (
        "純微台期 (10元/點)", 
        "期貨 + 選擇權賣方 (收租型)", 
        "純買方 (Long Call/Put)", 
        "價差策略 (Bull/Bear Spread)",
        "中性盤整 (鐵蝴蝶 Iron Butterfly)"
    )
)

# --- 核心邏輯：動態欄位映射 (與後端 update_data.py 命名空間對接) ---
# 1. 決定大腦前綴
if "3L-Strict" in engine_choice:
    brain_prefix = '3L_Strict'
elif "3L-Relaxed" in engine_choice:
    brain_prefix = '3L_Relaxed'
elif "MAD" in engine_choice:
    brain_prefix = 'MAD'
else:
    brain_prefix = 'Dir'

# 預設通用欄位
signal_col = f'Signal_{brain_prefix}'
pos_col = f'Pos_{brain_prefix}'

# 2. 決定工具尾綴並組合對應的 PnL 欄位
if "純微台期" in strategy_type:
    pnl_col = f'{brain_prefix}_Micro_PnL_TWD'
    desc = "【微台策略】無時間價值流失，單純追蹤日K趨勢，持有 10 天波段利潤。"
elif "賣方" in strategy_type:
    pnl_col = f'{brain_prefix}_Seller_PnL_TWD'
    desc = "【期貨+賣方收租】期貨部位搭配賣出價外選擇權，利用 10 天的時間價值貼補成本。"
elif "純買方" in strategy_type:
    pnl_col = f'{brain_prefix}_Buy_PnL_TWD'
    desc = "【純買方】追求高槓桿爆發力，但在 10 天長線持有下須承擔較大的時間價值損耗。"
elif "價差策略" in strategy_type:
    pnl_col = f'{brain_prefix}_Spread_PnL_TWD'
    desc = "【價差策略】透過賣出遠端合約降低成本，持有 10 天的抗震能力優於純買方。"
else:
    # 鐵蝴蝶為獨立策略，不依賴上述大腦前綴
    signal_col, pnl_col, pos_col = 'Signal_IB', 'IB_PnL_TWD', 'Pos_IB'
    desc = "【中性鐵蝴蝶】預期市場 10 天內進入狹幅盤整，賺取權利金點數。"

st.header(f"執行中：{engine_choice}")
st.info(desc)

# --- 防呆檢查 ---
if signal_col not in df.columns or pnl_col not in df.columns:
    st.error(f"🚨 找不到對應欄位 (訊號: {signal_col}, 損益: {pnl_col})。請確保 GitHub 上的 CSV 檔案已根據最新邏輯更新。")
    st.stop()

# -------------------------
# 2. 核心績效計算
# -------------------------
trades = df[df[signal_col] != 0].copy()
trade_results = trades[pnl_col].dropna()

if len(trade_results) > 0:
    win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
    ev = trade_results.mean()
    # 夏普值計算 (以 252 交易日年化)
    std_dev = trade_results.std()
    sharpe = (ev / std_dev) * np.sqrt(252) if std_dev != 0 else 0
    trades['Cumulative_PnL'] = trades[pnl_col].cumsum()
    total_pnl = trades['Cumulative_PnL'].iloc[-1]
else:
    win_rate = ev = sharpe = total_pnl = 0
    trades['Cumulative_PnL'] = 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("總交易次數", f"{len(trade_results)} 次")
col2.metric("策略勝率", f"{win_rate:.2f}%")
col3.metric("單筆期望值", f"NT$ {ev:.0f}")
col4.metric("策略夏普值", f"{sharpe:.2f}")
col5.metric("累積總損益", f"NT$ {total_pnl:,.0f}")

# -------------------------
# 3. 繪製圖表 (累積損益 & K線)
# -------------------------
st.subheader("💰 累積損益曲線 (持有期間：10 天波段)")
if len(trades) > 0:
    fig_pnl = go.Figure()
    line_color = 'rgba(50, 205, 50, 0.8)' if total_pnl > 0 else 'rgba(255, 69, 0, 0.8)'
    fig_pnl.add_trace(go.Scatter(
        x=trades.index, y=trades['Cumulative_PnL'], 
        mode='lines', fill='tozeroy', name='累積損益(TWD)', 
        line=dict(color=line_color)
    ))
    fig_pnl.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_pnl, use_container_width=True)

st.subheader("📊 近期進出場點位標示 (顯示最後 300 根 60K K線)")
plot_df = df.tail(300)
fig_k = go.Figure(data=[go.Candlestick(
    x=plot_df.index, open=plot_df['Open'], high=plot_df['High'], 
    low=plot_df['Low'], close=plot_df['Close'], name="台指K線"
)])

# 標示買賣點 (使用 Entry_Price 確保貼近實戰開盤進場)
for s, c, name, sym in [(1, 'red', '多頭佈局', 'triangle-up'), (-1, 'green', '空頭佈局', 'triangle-down')]:
    sigs = plot_df[plot_df[signal_col] == s]
    if not sigs.empty:
        fig_k.add_trace(go.Scatter(
            x=sigs.index, y=sigs['Entry_Price'], mode='markers+text', 
            marker=dict(symbol=sym, color=c, size=14), 
            name=name, text=sigs[pos_col].astype(int).astype(str) + (" 組" if "鐵蝴蝶" in strategy_type else " 口")
        ))

fig_k.update_layout(height=550, xaxis_rangeslider_visible=False)
st.plotly_chart(fig_k, use_container_width=True)

# -------------------------
# 4. 交易明細紀錄
# -------------------------
st.subheader("📋 交易紀錄與多空實證明細")
# 包含 YZ 波動率、趨勢分數與 MAD 指標供分析
display_cols = ['Close', 'YZ_Vol', 'Composite_Score', 'MAD_Value', signal_col, pos_col, pnl_col, 'Cumulative_PnL']

if not trades.empty:
    st.dataframe(trades[display_cols].sort_index(ascending=False).style.format({
        'Close': '{:.0f}', 'YZ_Vol': '{:.2%}', 'Composite_Score': '{:.2f}', 
        'MAD_Value': '{:.2f}', pnl_col: '{:.0f}', 'Cumulative_PnL': '{:.0f}'
    }))

# 提供資料下載
csv = df.to_csv().encode('utf-8-sig')
st.download_button(
    label="📥 下載完整回測數據 CSV (含複合策略指標)",
    data=csv,
    file_name='txf_final_backtest.csv',
    mime='text/csv',
)
