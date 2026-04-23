import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 自動監控系統", layout="wide")
service = SignalService()

# --- 側邊欄：初始設定 ---
with st.sidebar:
    st.header("🏢 模擬帳戶設定")
    # 初始資金設定為 5 萬元
    capital = st.number_input("起始資金 (TWD)", value=50000)
    date_range = st.date_input("分析期間", [datetime.now().date() - timedelta(days=59), datetime.now().date()])
    sl_pct = st.slider("固定停損 (%)", 0.5, 5.0, 1.5) / 100
    tp_pct = st.slider("移動停利 (%)", 0.5, 5.0, 1.5) / 100

st.title("🚀 My-Futures：自動模擬交易與損益追蹤")

with st.spinner("同步三框共振數據中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 1. 即時自動交易監控窗格
st.subheader("📡 即時模擬交易監控 (Auto-Tracking)")
c1, c2, c3, c4 = st.columns(4)
resonance = (res_30m['dir'] == res_60m['dir'] == res_1d['dir']) and res_30m['dir'] != '盤整'

with c1:
    st.metric("30M 訊號", res_30m['dir'])
with c2:
    st.metric("趨勢同步", "🔥 共振中" if resonance else "⚪ 觀望")
with c3:
    action = f"AUTO {'買入' if res_30m['dir']=='多' else '放空'}" if resonance else "等待訊號"
    st.write(f"**自動執行狀態：**\n{action}")
with c4:
    st.metric("當前 ATR 波動", f"{res_30m['atr_val']:.1f}")

# 2. 損益與回測分析窗格
st.divider()
if len(date_range) == 2:
    start, end = date_range
    perf = service.run_backtest(res_30m['df'], res_60m['df'], res_1d['df'], capital, str(start), str(end), sl_pct, tp_pct)
    
    if perf:
        st.subheader("📈 回測損益評估與權益曲線")
        
        # 績效卡片
        m1, m2, m3, m4 = st.columns(4)
        total_pnl = perf['final_equity'] - capital
        win_rate = (len(perf['trades'][perf['trades']['損益'] > 0]) / len(perf['trades'])) * 100
        
        m1.metric("累積淨損益", f"{total_pnl:,.0f} 元", delta=f"{(total_pnl/capital)*100:.1f}%")
        m2.metric("勝率 (Win Rate)", f"{win_rate:.1f}%")
        m3.metric("最大回撤 (MDD)", f"-{perf['mdd']:,.0f} 元")
        m4.metric("最終帳戶價值", f"{perf['final_equity']:,.0f} 元")

        # 累積權益曲線圖
        st.write("**累積權益變化 (Cumulative Equity)**")
        st.line_chart(perf['equity_curve'], color="#29b5e8")
        
        # 詳細回測紀錄
        with st.expander("📝 完整自動交易日誌 (回測 CSV)"):
            st.dataframe(perf['trades'], use_container_width=True)
            st.download_button("📥 下載績效報告", perf['trades'].to_csv().encode('utf-8-sig'), "pnl_report.csv")
    else:
        st.warning("此區間內無符合『三框一致』的共振訊號，系統目前處於自動觀望狀態。")
