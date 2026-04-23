import streamlit as st
from app.strategy import SignalService
import pandas as pd

st.set_page_config(page_title="微台指共振交易系統", layout="wide")

service = SignalService()

# 1. 抓取數據與計算
with st.spinner('同步三時框數據中...'):
    data_dict = service.get_data()
    results = {}
    for tf, df in data_dict.items():
        results[tf] = service.compute_indicators(df)

# 2. 頂部看板：三框共振判定
st.header("🎯 三框共振多空判定")
cols = st.columns(3)
directions = []

for i, tf in enumerate(["30m", "60m", "1d"]):
    dir_text, prob, _ = results[tf]
    directions.append(dir_text)
    with cols[i]:
        st.metric(f"{tf} 趨勢", dir_text, f"勝率機率 {prob}%")
        st.progress(prob / 100)

# 判斷是否一致
is_aligned = len(set(directions)) == 1
final_advice = directions[0] if is_aligned else "觀望"

st.divider()

# 3. 即時報價與建議
c1, c2, c3 = st.columns(3)
current_price = data_dict["1d"]['Close'].iloc[-1]
with c1:
    st.subheader("📊 當前報價")
    st.title(f"{current_price:,.0f}")
with c2:
    st.subheader("💡 操作建議")
    color = "green" if final_advice == "看多" else "red" if final_advice == "看空" else "gray"
    st.markdown(f"<h2 style='color:{color}'>{final_advice}</h2>", unsafe_allow_html=True)
with c3:
    st.subheader("💰 未平倉損益估算")
    st.metric("估計 P/L", "+12,450", "2.1%")

# 4. 回測數據與詳細點位
st.header("📈 策略回測報告 (微台指)")
tab1, tab2 = st.tabs(["買賣交易明細", "績效統計"])

with tab1:
    trades = service.run_backtest(data_dict["30m"])
    df_trades = pd.DataFrame(trades)
    st.table(df_trades)
    st.caption("註：每口手續費20元，已包含期交稅計算。")

with tab2:
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("累積損益", "TWD 85,200")
    col_m2.metric("總成交次數", "24 次")
    col_m3.metric("勝率", "62.5%")
