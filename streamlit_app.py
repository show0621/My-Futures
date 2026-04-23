import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 專業量化監控", layout="wide")

@st.cache_resource
def get_service():
    return SignalService()

service = get_service()

st.title("🏹 My-Futures：高還原度實戰交易系統")

with st.sidebar:
    st.header("資金與風險設定")
    # 100,000 萬元 = 10 億 TWD
    capital_val = st.number_input("起始資金 (萬元)", value=100000)
    capital = capital_val * 10000
    date_range = st.date_input("回測區間 (30M 最長 60天)", [datetime.now() - timedelta(days=59), datetime.now()])
    st.divider()
    stop_loss = st.slider("固定停損 (%)", 0.5, 5.0, 2.0) / 100
    trailing = st.slider("移動停利 (%)", 0.5, 3.0, 1.5) / 100

if len(date_range) == 2:
    start_dt, end_dt = date_range
    with st.spinner("同步數據與回測運算中..."):
        df_raw = service.fetch_data("30m", "60d")
        res = service.compute_indicators(df_raw)
        perf = service.run_backtest(res['df'], capital, str(start_dt), str(end_dt), stop_loss, trailing)

    # 1. 實時水位監控
    st.subheader("🛡️ 帳戶水位與保證金監控")
    curr_price = float(df_raw['close'].iloc[-1])
    total_pnl = perf['total_pnl'] if perf else 0
    current_equity = capital + total_pnl
    used_margin = service.initial_margin # 預設一口
    margin_level = (current_equity / used_margin) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("權益總額", f"{current_equity:,.0f}")
    c2.metric("使用保證金", f"{used_margin:,.0f}")
    c3.metric("保證金維持率", f"{margin_level:.0f}%")
    c4.metric("波動狀態", "符合進場" if res['df']['vol_ok'].iloc[-1] else "波動太小", delta_color="normal")

    st.divider()

    if perf:
        # 2. 專業績效指標
        st.subheader("📈 策略核心績效")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("夏普比率", f"{perf['sharpe']:.2f}")
        m2.metric("最大回測 (MDD)", f"{perf['mdd']:,.0f}", delta_color="inverse")
        m3.metric("期望值 (每筆)", f"{perf['expectancy']:,.0f}")
        m4.metric("平均盈虧比", f"{perf['pl_ratio']:.2f}")
        m5.metric("總報酬率", f"{(total_pnl/capital)*100:.2f}%")

        # 3. 診斷與建議
        col_a, col_b = st.columns(2)
        with col_a:
            st.info("### 🤖 策略診斷報告")
            if perf['expectancy'] > 500:
                st.success(f"**診斷結果：這是一套可獲利的系統。**\n正期望值 ({perf['expectancy']:,.0f}) 顯示長期執行具備獲利優勢。")
            else:
                st.error("**診斷結果：獲利能力不足。**\n期望值過低或為負，請調整停損比例或優化進場過濾。")
        
        with col_b:
            st.warning("### 🛠️ 策略修正建議")
            if perf['win_rate'] < 0.4:
                st.write("- **勝率偏低：** 建議調寬停損至 3% 以上，給趨勢更多波動空間。")
            if perf['pl_ratio'] < 1.5:
                st.write("- **盈虧比不佳：** 建議調緊移動停利，或利用 60M 時框作為第二層趨勢確認。")

        # 4. 資料下載
        st.divider()
        csv = perf['trades'].to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載完整回測報告 (CSV)", csv, "backtest_report.csv", "text/csv")
        st.dataframe(perf['trades'], use_container_width=True)
    else:
        st.warning("所選區間內無符合 ATR 波動與 EMA 趨勢之交易訊號。")
