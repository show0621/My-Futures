import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 專業過濾版", layout="wide")
service = SignalService()

st.title("🛡️ My-Futures：波動過濾與結算避險系統")

with st.sidebar:
    st.header("回測參數設定")
    capital = st.number_input("起始資金 (萬元)", value=100000) * 10000
    date_range = st.date_input("回測區間", [datetime.now() - timedelta(days=59), datetime.now()])
    stop_loss = st.slider("停損 (%)", 0.5, 5.0, 2.0) / 100
    trailing = st.slider("停利 (%)", 0.5, 3.0, 1.5) / 100

if len(date_range) == 2:
    start, end = date_range
    df_raw = service.fetch_data("30m", "60d")
    res = service.compute_indicators(df_raw)
    df_trades = service.run_backtest(res['df'], capital, str(start), str(end), stop_loss, trailing)

    # 1. 狀態看板
    c1, c2, c3 = st.columns(3)
    c1.metric("當前趨勢", res['dir'])
    c2.metric("波動過濾狀態", "符合進場" if res['df']['vol_ok'].iloc[-1] else "波動太小")
    c3.metric("近期結算日", "避開交易" if service._is_expiry_day(datetime.now()) else "正常交易")

    st.divider()

    if df_trades is not None:
        # 2. 績效統計
        wins = df_trades[df_trades['損益'] > 0]
        expectancy = (len(wins)/len(df_trades) * wins['損益'].mean()) - (len(df_trades[df_trades['損益']<=0])/len(df_trades) * abs(df_trades[df_trades['損益']<=0]['損益'].mean()))
        
        m1, m2, m3 = st.columns(3)
        m1.metric("累積損益", f"{df_trades['損益'].sum():,}")
        m2.metric("每筆期望值", f"{expectancy:,.1f}")
        m3.metric("勝率", f"{len(wins)/len(df_trades)*100:.1f}%")

        # 3. 下載與日誌
        st.download_button("📥 下載完整 CSV 報告", df_trades.to_csv().encode('utf-8-sig'), "report.csv")
        st.dataframe(df_trades, use_container_width=True)
        
        # 4. 診斷報告
        st.subheader("🤖 策略診斷")
        if expectancy > 50:
            st.success(f"期望值達標 ({expectancy:,.0f})：這套『EMA+ATR過濾』策略在歷史數據中具備實戰獲利能力。")
        else:
            st.error(f"期望值過低：即使加入了波動過濾，目前的獲利仍無法有效覆蓋風險。")
    else:
        st.warning("此區間無交易訊號。")
