import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 即時監控儀表板", layout="wide")
service = SignalService()

st.title("📊 My-Futures：多時框共振監控儀表板")

# 1. 資料抓取與計算
with st.spinner("同步 30M/60M/1D 數據中..."):
    # 抓取數據
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    
    # 計算各時框指標
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 2. 多時框即時監控儀表板
st.subheader("🛰️ 即時多時框監控")
c1, c2, c3 = st.columns(3)

def display_gauge(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.markdown(f"### {title}")
        st.markdown(f"<h2 style='color:{color}'>{res['dir']} ({res['prob']}%)</h2>", unsafe_allow_html=True)
        st.progress(res['prob'] / 100)
        st.caption(f"波動過濾：{'✅ 通過' if res['vol_ok'] else '❌ 波動過小'}")

display_gauge(c1, "30分K (極短線)", res_30m)
display_gauge(c2, "60分K (短線)", res_60m)
display_gauge(c3, "日K (中長線趨勢)", res_1d)



# 3. 綜合分析報告與操作建議
st.divider()
st.subheader("📝 策略分析報告與建議")

# 判斷共振
all_dirs = [res_30m['dir'], res_60m['dir'], res_1d['dir']]
is_resonance = len(set(all_dirs)) == 1

col_report, col_action = st.columns([2, 1])

with col_report:
    st.write("**當前行情分析：**")
    if is_resonance:
        st.success(f"🔥 **三框共振確認**：目前 30M、60M 與日線趨勢高度一致，均顯示為『{all_dirs[0]}』方強勢。")
    else:
        st.warning(f"⚠️ **趨勢分歧**：目前時框方向為 {all_dirs}，建議等待信號同步。")
    
    st.write(f"- **趨勢強度**：平均機率 {sum([res_30m['prob'], res_60m['prob'], res_1d['prob']])/3:.1f}%")
    st.write(f"- **波動環境**：{'當前波動率足以支撐趨勢發動。' if res_30m['vol_ok'] else '市場處於縮頭整理，容易產生假突破。'}")

with col_action:
    st.write("**🎯 操作建議：**")
    if is_resonance and res_30m['vol_ok']:
        if all_dirs[0] == "多":
            st.button("🟢 建議做多", use_container_width=True)
        else:
            st.button("🔴 建議放空", use_container_width=True)
    else:
        st.button("⚪ 觀望 / 收手", use_container_width=True)
    
    st.caption("建議根據期望值 CSV 報告調整部位大小。")

# 4. 回測區間與 CSV (保留原本功能)
with st.expander("展開回測數據與 CSV 下載"):
    capital = 1000000000 # 10億
    perf = service.run_backtest(res_30m['df'], capital, str(datetime.now()-timedelta(days=30)), str(datetime.now()), 0.02, 0.015)
    if perf:
        st.write(f"近期期望值：{perf['expectancy']:,.0f}")
        st.download_button("📥 下載回測報告", perf['trades'].to_csv().encode('utf-8-sig'), "backtest.csv")
        st.dataframe(perf['trades'], use_container_width=True)
