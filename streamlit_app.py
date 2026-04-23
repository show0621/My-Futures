import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 三框共振版", layout="wide")
service = SignalService()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 實戰參數與回測期間")
    capital_val = st.number_input("起始資金 (萬元)", value=100)
    capital = capital_val * 10000
    date_range = st.date_input("選擇回測區間", [datetime.now() - timedelta(days=59), datetime.now()])
    
    st.divider()
    # 預設縮小 0.5% 至 1.5%
    sl_pct = st.slider("固定停損 (%)", 0.5, 10.0, 1.5) / 100 
    tp_pct = st.slider("移動停利 (%)", 0.5, 5.0, 1.5) / 100
    
    st.info("### 🛡️ 策略核心：三框共振\n1. **進場**：30M/60M/1D 訊號必須完全一致（全多或全空）。\n2. **目的**：利用大時框過濾掉小時框的假訊號，大幅降低 MDD。")

st.title("🏹 My-Futures：三框共振實戰監控")

# 1. 抓取數據
with st.spinner("同步 30M/60M/1D 數據中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 2. 監控看板
st.subheader("🛰️ 即時時框同步狀態")
c1, c2, c3 = st.columns(3)

def display_gauge(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.markdown(f"### {title}")
        st.markdown(f"<h1 style='color:{color}'>{res['dir']}</h1>", unsafe_allow_html=True)
        st.write(f"當前 ATR: **{res['atr_val']:.1f}**")
        st.caption(f"波動狀態：{'✅ 通過' if res['vol_ok'] else '❌ 波動過小'}")

display_gauge(c1, "30分K (極短線)", res_30m)
display_gauge(c2, "60分K (短線)", res_60m)
display_gauge(c3, "日K (主趨勢趨勢)", res_1d)

# 3. 績效統計與回測
st.divider()
if len(date_range) == 2:
    start, end = date_range
    # 執行三框共振回測
    perf = service.run_backtest(
        res_30m['df'], res_60m['df'], res_1d['df'], 
        capital, str(start), str(end), sl_pct, tp_pct
    )
    
    if perf:
        st.subheader(f"📊 三框共振績效報告 ({start} 至 {end})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("累積損益", f"{perf['total_pnl']:,.0f} 元")
        m2.metric("最大回撤 (MDD)", f"{perf['mdd']:,.0f} 元", delta_color="inverse")
        m3.metric("夏普比率", f"{perf['sharpe']:.2f}")
        m4.metric("勝率", f"{perf['win_rate']*100:.1f}%")

        with st.expander("📝 查看詳細交易紀錄 (已過濾非共振訊號)"):
            st.dataframe(perf['trades'], use_container_width=True)
            st.download_button("📥 下載共振回測報告", perf['trades'].to_csv().encode('utf-8-sig'), "resonance_backtest.csv")
    else:
        st.warning("當前區間內無符合『三框一致』的共振訊號，建議空手觀望。")
