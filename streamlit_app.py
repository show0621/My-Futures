import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 專業版", layout="wide")
service = SignalService()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 實戰參數與回測期間")
    capital_val = st.number_input("起始資金 (萬元)", value=100)
    capital = capital_val * 10000
    
    # 新增回測期間選擇
    today = datetime.now()
    date_range = st.date_input("選擇回測區間", [today - timedelta(days=59), today])
    
    st.divider()
    sl_pct = st.slider("固定停損 (%)", 0.5, 10.0, 2.0) / 100
    tp_pct = st.slider("移動停利 (%)", 0.5, 5.0, 1.5) / 100
    
    st.info("### 📖 雙向策略說明\n- **進場**：EMA快線突破慢線(多)或跌破(空)，且當前波動 > 20日平均。\n- **出場**：觸發停損停利、滿7天或每月第三個週三結算日。")

st.title("🏹 My-Futures：雙向趨勢監控儀表板")

# 1. 抓取數據
with st.spinner("數據同步中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 2. 監控看板 (新增 ATR 與 20日 ATR)
st.subheader("🛰️ 即時多時框監控")
c1, c2, c3 = st.columns(3)

def display_gauge(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.markdown(f"### {title}")
        st.markdown(f"<h1 style='color:{color}'>{res['dir']} ({res['prob']}%)</h1>", unsafe_allow_html=True)
        st.write(f"當前 ATR: **{res['atr_val']:.1f}** / 20日 ATR: **{res['atr_ma_val']:.1f}**")
        st.progress(res['prob'] / 100)
        st.caption(f"波動過濾：{'✅ 通過' if res['vol_ok'] else '❌ 波動過小'}")

display_gauge(c1, "30分K (極短線)", res_30m)
display_gauge(c2, "60分K (短線)", res_60m)
display_gauge(c3, "日K (主趨勢)", res_1d)

# 3. 績效統計與回測
st.divider()
if len(date_range) == 2:
    start, end = date_range
    perf = service.run_backtest(res_30m['df'], capital, str(start), str(end), sl_pct, tp_pct)
    
    if perf:
        st.subheader(f"📊 績效報告 ({start} 至 {end})")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("累積損益", f"{perf['total_pnl']:,.0f} 元")
        m2.metric("最大回撤 (MDD)", f"{perf['mdd']:,.0f} 元", delta_color="inverse")
        m3.metric("最大單筆報酬", f"{perf['max_ret']*100:.2f}%")
        m4.metric("夏普比率 (Sharpe)", f"{perf['sharpe']:.2f}")

        with st.expander("📝 查看詳細交易紀錄 (含放空策略)"):
            st.download_button("📥 下載回測 CSV", perf['trades'].to_csv().encode('utf-8-sig'), "backtest.csv")
            st.dataframe(perf['trades'], use_container_width=True)
    else:
        st.warning("此區間內無交易訊號。")
