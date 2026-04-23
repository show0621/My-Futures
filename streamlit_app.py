import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 高還原度回測", layout="wide")
service = SignalService()

st.title("📊 My-Futures：專業回測與資料匯出")

# 側邊欄：回測區間選擇
with st.sidebar:
    st.header("回測參數設定")
    capital = st.number_input("起始資金 (萬元)", value=100000) * 10000
    
    # 日期選擇器
    today = datetime.now()
    default_start = today - timedelta(days=59)
    date_range = st.date_input("選擇回測期間 (30M 最長 60天)", [default_start, today])
    
    stop_loss = st.slider("固定停損 (%)", 0.5, 5.0, 2.0) / 100
    trailing = st.slider("追蹤停利 (%)", 0.5, 3.0, 1.5) / 100

if len(date_range) == 2:
    start_dt, end_dt = date_range
    with st.spinner("讀取歷史數據中..."):
        df_raw = service.fetch_data("30m", "60d") # 30M 限額 60天
        df_ind = service.compute_indicators(df_raw)
        trades_df = service.run_backtest(df_ind, capital, str(start_dt), str(end_dt), stop_loss, trailing)

    if trades_df is not None:
        # 1. 下載功能
        csv = trades_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載完整回測報告 (CSV)",
            data=csv,
            file_name=f"backtest_{start_dt}_to_{end_dt}.csv",
            mime="text/csv",
        )

        # 2. 顯示數據表
        st.subheader("📝 詳細交易日誌")
        st.dataframe(trades_df, use_container_width=True)

        # 3. 策略診斷與還原度分析
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.info("### 🧐 回測還原度檢測")
            st.write("1. **滑價補償：** 已手動加入單邊 2 點滑價，模擬實盤掛單成本。")
            st.write("2. **稅費計算：** 已包含萬分之 0.2 期交稅與單邊 20 元手續費。")
            st.write("3. **價格誤差：** 使用 `^TWII` 加權指數作為代用，**未包含期現貨價差 (Basis)**。")
        
        with c2:
            st.warning("### 🔄 轉倉處理提醒")
            st.write("1. **價差跳空：** 台指期每月結算會產生 100-200 點不等的除息或價差缺口。")
            st.write("2. **回測偏差：** 本回測使用連續價格，**未扣除轉倉當天的跳空**，實務上獲利可能會略低於此數據。")
            st.write("**建議：** 若回測淨利潤低於轉倉缺口總和，該策略不具備實戰價值。")
    else:
        st.error("所選期間內無交易訊號。")
