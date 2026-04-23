import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 實戰交易系統", layout="wide")

# 注意：如果發生 TypeError，請手動點擊右上角 Clear Cache
@st.cache_resource
def get_service():
    return SignalService()

service = get_service()

st.title("🏹 My-Futures：高還原度量化監控系統")

with st.sidebar:
    st.header("資金與風險管理")
    # 100,000 萬元 = 10 億 TWD
    capital_val = st.number_input("起始資金 (萬元)", value=100000)
    capital = capital_val * 10000
    date_range = st.date_input("回測區間 (30M 最長 60天)", [datetime.now() - timedelta(days=59), datetime.now()])
    st.divider()
    stop_loss = st.slider("固定停損 (%)", 0.5, 5.0, 2.0) / 100
    trailing = st.slider("移動停利 (%)", 0.5, 3.0, 1.5) / 100

if len(date_range) == 2:
    start_dt, end_dt = date_range
    with st.spinner("同步數據與執行回測中..."):
        df_raw = service.fetch_data("30m", "60d")
        res = service.compute_indicators(df_raw)
        perf = service.run_backtest(res['df'], capital, str(start_dt), str(end_dt), stop_loss, trailing)

    # 1. 帳戶水位看板
    st.subheader("🛡️ 實時帳戶水位")
    curr_price = float(df_raw['close'].iloc[-1])
    total_pnl = perf['total_pnl'] if perf else 0
    current_equity = capital + total_pnl
    margin_level = (current_equity / service.initial_margin) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("權益總額", f"{current_equity:,.0f}")
    c2.metric("使用保證金 (1口)", f"{service.initial_margin:,.0f}")
    c3.metric("保證金維持率", f"{margin_level:.0f}%")
    c4.metric("波動狀態", "符合進場" if res['df']['vol_ok'].iloc[-1] else "波動太小", delta_color="normal")

    st.divider()

    if perf:
        # 2. 核心績效數據
        st.subheader("📈 策略績效診斷")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("夏普比率 (Sharpe)", f"{perf['sharpe']:.2f}")
        m2.metric("最大回測 (MDD)", f"{perf['mdd']:,.0f}", delta_color="inverse")
        m3.metric("每筆期望值", f"{perf['expectancy']:,.0f}")
        m4.metric("盈虧比", f"{perf['pl_ratio']:.2f}")
        m5.metric("勝率", f"{perf['win_rate']*100:.1f}%")

        # 3. 實戰建議
        col_a, col_b = st.columns(2)
        with col_a:
            st.info("### 🤖 策略診斷結論")
            if perf['expectancy'] > 500:
                st.success(f"**結論：具備獲利能力。**\n正期望值代表長期執行能產生淨利。")
            else:
                st.error("**結論：目前無法獲利。**\n請優化波動過濾或調寬停損，以提升盈虧比。")
        
        with col_b:
            st.warning("### 🛠️ 策略修正建議")
            if perf['win_rate'] < 0.4:
                st.write("- **勝率過低：** 可能是 30M 雜訊太多，建議增加 60M 趨勢一致性過濾。")
            if perf['pl_ratio'] < 1.2:
                st.write("- **盈虧比不足：** 建議調緊移動停利，減少獲利回吐。")

        # 4. CSV 下載與明細
        st.divider()
        csv = perf['trades'].to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載完整 CSV 回測報告", csv, "backtest_report.csv", "text/csv")
        st.dataframe(perf['trades'], use_container_width=True)
    else:
        st.warning("所選區間內無符合條件的成交紀錄。")
