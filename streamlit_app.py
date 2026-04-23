import streamlit as st
import pandas as pd
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 實戰監控", layout="wide")
service = SignalService()

st.title("🚀 My-Futures 量化實戰分析儀表板")

# 側邊欄設定
with st.sidebar:
    st.header("資金與風險設定")
    # 100000 萬元 = 10 億，這裡預設為使用者輸入的值
    capital = st.number_input("起始資金 (萬元)", value=100000) * 10000
    stop_loss = st.slider("停損比例 (%)", 0.5, 10.0, 2.0) / 100
    trailing = st.slider("追蹤停利 (%)", 0.5, 5.0, 1.5) / 100

with st.spinner("正在進行大數據回測..."):
    df_raw = service.fetch_data("30m", "60d")
    analysis = service.compute_indicators(df_raw)
    perf = service.run_backtest(analysis['df'], capital, stop_loss, trailing)

# 1. 頂部核心指標
if perf:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("夏普比率 (Sharpe)", f"{perf['sharpe']:.2f}")
    m2.metric("最大回測 (MDD)", f"{perf['mdd']:,.0f}", delta_color="inverse")
    m3.metric("期望值 (每筆)", f"{perf['expectancy']:,.1f} 元")
    m4.metric("平均盈虧比", f"{perf['profit_loss_ratio']:.2f}")

    st.divider()

    # 2. 保證金與水位監控
    st.subheader("🛡️ 實時帳戶水位")
    curr_price = float(df_raw['close'].iloc[-1])
    current_equity = capital + perf['total_pnl']
    used_margin = service.initial_margin # 假設一口
    margin_level = (current_equity / used_margin) * 100
    
    c1, c2, c3 = st.columns(3)
    c1.metric("當前權益總額", f"{current_equity:,.0f}")
    c2.metric("使用保證金", f"{used_margin:,.0f}")
    c3.metric("保證金維持率", f"{margin_level:.1f}%", help="低於 120% 有斷頭風險")
    
    # 3. 績效分析與建議
    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("### 績效數據表")
        st.write(f"- **最大單筆報酬:** {perf['max_ret']*100:.2f}%")
        st.write(f"- **平均每筆報酬:** {perf['avg_ret']*100:.2f}%")
        st.write(f"- **勝率:** {perf['win_rate']*100:.1f}%")
        
    with col_b:
        st.write("### 🤖 策略診斷報告")
        is_profitable = perf['expectancy'] > 0
        if is_profitable:
            st.success(f"**結論：此策略具備賺錢潛力。**\n期望值為正 ({perf['expectancy']:.1f})，長期執行具備獲利基礎。")
        else:
            st.error("**結論：此策略目前無法獲利。**\n期望值為負，請務必修正參數。")
            
        st.info("### 🛠️ 建議修正方向")
        if perf['win_rate'] < 0.4:
            st.warning("⚠️ 勝率過低：建議加入 RSI 超買超賣過濾，或調寬固定停損門檻。")
        if perf['sharpe'] < 1:
            st.warning("⚠️ 風險波動過大：建議調緊移動停利，以鎖住利潤。")
else:
    st.error("數據不足，無法生成分析報告。")
