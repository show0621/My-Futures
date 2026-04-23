import streamlit as st
import pandas as pd
from app.strategy import SignalService

st.set_page_config(page_title="微台指三框共振監控", layout="wide")

@st.cache_resource
def get_service():
    return SignalService()

service = get_service()

st.title("🎯 微台指：三框共振與動態停利系統")

with st.spinner("同步數據中..."):
    # 抓取原始數據
    df_30m_raw = service.fetch_data("30m", "60d")
    df_60m_raw = service.fetch_data("60m", "60d")
    df_1d_raw = service.fetch_data("1d", "2y")
    
    # 運算指標並獲取含指標的 DataFrame
    res_30m = service.compute_indicators(df_30m_raw)
    res_60m = service.compute_indicators(df_60m_raw)
    res_1d = service.compute_indicators(df_1d_raw)
    
    # 這裡我們獲取帶有 EMA 的 DataFrame 用於後續顯示或回測
    df_30m_final = res_30m['df']

st.subheader("🛰️ 時框同步狀態")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("30M 趨勢", res_30m['dir'], f"強度 {res_30m['prob']}%")
with c2:
    st.metric("60M 趨勢", res_60m['dir'], f"強度 {res_60m['prob']}%")
with c3:
    st.metric("1D 趨勢", res_1d['dir'], f"強度 {res_1d['prob']}%")

st.divider()

# 即時報價顯示
try:
    curr_price = float(df_1d_raw['close'].iloc[-1])
except:
    curr_price = 0.0

col_m1, col_m2 = st.columns(2)
with col_m1:
    st.header(f"💰 當前報價：{curr_price:,.0f}")
with col_m2:
    all_dirs = [res_30m['dir'], res_60m['dir'], res_1d['dir']]
    if all(d == "多" for d in all_dirs):
        advice, color = "強烈看多 (三框共振)", "green"
    elif all(d == "空" for d in all_dirs):
        advice, color = "強烈看空 (三框共振)", "red"
    else:
        advice, color = "方向不一 (觀望)", "gray"
    st.markdown(f"### 操作建議：<span style='color:{color}'>{advice}</span>", unsafe_allow_html=True)

# 回測明細
st.subheader("📈 策略回測明細 (30M 基礎)")
# 這裡傳入已經運算過指標的 df_30m_final
trades = service.run_backtest(df_30m_final)

if trades:
    df_t = pd.DataFrame(trades)
    st.dataframe(df_t, use_container_width=True)
    
    total_pnl = df_t['淨損益'].sum()
    win_rate = (len(df_t[df_t['淨損益'] > 0]) / len(df_t)) * 100
    
    m1, m2, m3 = st.columns(3)
    m1.metric("累積淨損益", f"TWD {total_pnl:,}")
    m2.metric("總交易次數", f"{len(df_t)} 次")
    m3.metric("勝率", f"{win_rate:.1f}%")
else:
    st.info("近期尚無符合條件的成交紀錄。")

st.caption("備註：回測包含 7天強平、移動停利 1.5% 與固定停損 2% 邏輯。")
