import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 三框共振版", layout="wide")
service = SignalService()

with st.sidebar:
    st.header("⚙️ 實戰參數")
    capital_val = st.number_input("起始資金 (萬元)", value=100)
    capital = capital_val * 10000
    date_range = st.date_input("選擇回測區間", [datetime.now().date() - timedelta(days=59), datetime.now().date()])
    
    st.divider()
    sl_pct = st.slider("固定停損 (%)", 0.5, 10.0, 1.5) / 100 
    tp_pct = st.slider("移動停利 (%)", 0.5, 5.0, 1.5) / 100
    
    st.warning("### 🚨 強制平倉保險絲\n1. **金額停損**：20,000 元。\n2. **三框同步**：30M/60M/1D 必須完全一致。")

st.title("🏹 My-Futures：三框共振實戰監控")

with st.spinner("同步數據中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 監控看板
st.subheader("🛰️ 時框同步狀態")
c1, c2, c3 = st.columns(3)
def display_box(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.markdown(f"### {title}: <span style='color:{color}'>{res['dir']}</span>", unsafe_allow_html=True)
        st.caption(f"ATR: {res['atr_val']:.1f}")

display_box(c1, "30M", res_30m)
display_box(c2, "60M", res_60m)
display_box(c3, "日K", res_1d)

st.divider()
if len(date_range) == 2:
    start, end = date_range
    # 將 date 轉為 string，由 SignalService 處理時區中和
    perf = service.run_backtest(
        res_30m['df'], res_60m['df'], res_1d['df'], 
        capital, str(start), str(end), sl_pct, tp_pct
    )
    
    if perf:
        st.subheader("📊 績效報告 (三框共振 + 金額停損)")
        m1, m2 = st.columns(2)
        m1.metric("累積損益", f"{perf['total_pnl']:,.0f} 元")
        m2.metric("最大回撤 (MDD)", f"{perf['mdd']:,.0f} 元", delta_color="inverse")
        
        st.dataframe(perf['trades'], use_container_width=True)
        st.download_button("📥 下載報告", perf['trades'].to_csv().encode('utf-8-sig'), "backtest_final.csv")
    else:
        st.warning("當前區間內無符合『三框一致』的共振訊號。")
