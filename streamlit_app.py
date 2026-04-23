import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 實戰監控系統", layout="wide")

@st.cache_resource
def get_service():
    return SignalService()

service = get_service()

st.title("🏹 My-Futures：專業量化監控與回測系統")

# 側邊欄設定
with st.sidebar:
    st.header("資金與風險設定")
    capital_val = st.number_input("起始資金 (萬元)", value=100000) # 100,000 萬元 = 10 億
    capital = capital_val * 10000
    
    # 日期區間
    today = datetime.now()
    default_start = today - timedelta(days=59)
    date_range = st.date_input("回測區間 (30M 最長 60天)", [default_start, today])
    
    st.divider()
    stop_loss = st.slider("固定停損 (%)", 0.5, 5.0, 2.0) / 100
    trailing = st.slider("移動停利 (%)", 0.5, 3.0, 1.5) / 100

if len(date_range) == 2:
    start_dt, end_dt = date_range
    with st.spinner("同步數據與運算績效中..."):
        df_raw = service.fetch_data("30m", "60d")
        res = service.compute_indicators(df_raw)
        perf = service.run_backtest(res['df'], capital, str(start_dt), str(end_dt), stop_loss, trailing)

    # 1. 頂部看板：帳戶水位
    st.subheader("🛡️ 帳戶即時水位")
    curr_price_val = float(df_raw['close'].iloc[-1])
    total_pnl = perf['total_pnl'] if perf else 0
    current_equity = capital + total_pnl
    margin_level = (current_equity / service.initial_margin) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("權益總額", f"{current_equity:,.0f}")
    c2.metric("當前報價 (日盤)", f"{curr_price_val:,.0f}")
    c3.metric("保證金維持率", f"{margin_level:.0f}%")
    c4.metric("波動狀態", "符合進場" if res['df']['vol_ok'].iloc[-1] else "波動太小", delta_color="normal")

    st.divider()

    if perf:
        # 2. 核心績效數據
        st.subheader("📊 策略實戰診斷")
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
                st.success(f"**結論：具備獲利優勢。**\n正期望值 ({perf['expectancy']:,.0f}) 顯示長期執行具備獲利潛力。")
            else:
                st.error("**結論：獲利能力不足。**\n期望值過低，建議調寬停損門檻或優化進場指標。")
        
        with col_b:
            st.warning("### 🛠️ 策略優化方向")
            st.write(f"- **避開結算日：** 系統已自動排除每月第三個週三，降低換倉風險。")
            if perf['win_rate'] < 0.4:
                st.write(f"- **勝率提醒：** 30M 雜訊較多，建議結合 60M 趨勢作為雙重過濾。")

        # 4. CSV 下載與時區轉換顯示
        st.divider()
        st.subheader("📝 詳細交易紀錄 (台灣時間)")
        
        df_trades = perf['trades'].copy()
        # 轉換時區至台灣時間 UTC+8
        df_trades['進場時間'] = pd.to_datetime(df_trades['進場時間']).dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M')
        df_trades['出場時間'] = pd.to_datetime(df_trades['出場時間']).dt.tz_convert('Asia/Taipei').dt.strftime('%Y-%m-%d %H:%M')
        
        # 準備下載檔案
        csv_data = df_trades.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載完整回測報告 (CSV)", csv_data, f"backtest_{start_dt}.csv", "text/csv")
        
        st.dataframe(df_trades, use_container_width=True)
    else:
        st.warning("所選區間內無符合條件（趨勢一致、波動足夠且非結算日）的交易訊號。")
