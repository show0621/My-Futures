import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 專業優化版", layout="wide")
service = SignalService()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 實戰參數與回測期間")
    capital_val = st.number_input("起始資金 (萬元)", value=100)
    capital = capital_val * 10000
    date_range = st.date_input("選擇回測區間", [datetime.now() - timedelta(days=59), datetime.now()])
    
    st.divider()
    # 將預設值從 2.0% 調降至 1.5% (回應縮小 0.5% 的需求)
    sl_pct = st.slider("固定停損 (%)", 0.5, 10.0, 1.5) / 100 
    tp_pct = st.slider("移動停利 (%)", 0.5, 5.0, 1.5) / 100
    
    st.info("### 🛡️ 優化說明\n1. **日線過濾**：放空僅在日線空頭時觸發。\n2. **停損優化**：預設停損降至 1.5%，旨在降低 MDD。")

st.title("🏹 My-Futures：雙向趨勢監控 (含日線過濾)")

# 1. 抓取數據
with st.spinner("數據同步中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    res_30m = service.compute_indicators(df_30m)
    res_1d = service.compute_indicators(df_1d)

# 2. 監控看板
st.subheader("🛰️ 即時監控")
c1, c2 = st.columns(2)
with c1:
    color = "green" if res_30m['dir'] == "多" else "red" if res_30m['dir'] == "空" else "gray"
    st.markdown(f"### 30分K 狀態：<span style='color:{color}'>{res_30m['dir']}</span>", unsafe_allow_html=True)
with c2:
    color_1d = "green" if res_1d['dir'] == "多" else "red" if res_1d['dir'] == "空" else "gray"
    st.markdown(f"### 日K 趨勢：<span style='color:{color_1d}'>{res_1d['dir']}</span>", unsafe_allow_html=True)

# 3. 回測績效
st.divider()
if len(date_range) == 2:
    start, end = date_range
    # 傳入 df_1d 進行趨勢過濾
    perf = service.run_backtest(res_30m['df'], df_1d, capital, str(start), str(end), sl_pct, tp_pct)
    
    if perf:
        st.subheader(f"📊 優化後績效報告 ({start} 至 {end})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("累積損益", f"{perf['total_pnl']:,.0f} 元")
        m2.metric("最大回撤 (MDD)", f"{perf['mdd']:,.0f} 元", delta_color="inverse")
        m3.metric("勝率", f"{perf['win_rate']*100:.1f}%")
        m4.metric("夏普比率", f"{perf['sharpe']:.2f}")

        with st.expander("📝 交易明細 (已加入日線過濾)"):
            st.dataframe(perf['trades'], use_container_width=True)
            st.download_button("📥 下載回測 CSV", perf['trades'].to_csv().encode('utf-8-sig'), "backtest_v2.csv")
    else:
        st.warning("此區間內無交易訊號。")
