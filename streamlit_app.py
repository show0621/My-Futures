import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 選擇權實戰", layout="wide")
service = SignalService()

# --- 側邊欄：進場追蹤設定 ---
with st.sidebar:
    st.header("💼 上班族部位追蹤")
    st.info("若你已照建議買進，請輸入下方資訊追蹤損益：")
    entry_idx = st.number_input("進場時的指數點位", value=0.0)
    entry_cost = st.number_input("買入權利金點數 (例如 150)", value=0.0)
    
    st.divider()
    st.warning("### 💡 上班族必讀\n選擇權『買方』每日會流逝時間價值 (Theta)，若大盤盤整超過 3 天，建議即使沒賠錢也要考慮撤離。")

st.title("🛡️ My-Futures：選擇權趨勢共振系統")

with st.spinner("同步三框數據中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 1. 選擇權即時建議 (核心區塊)
st.subheader("🎯 當前選擇權操作建議")
opt = res_30m['opt_rec']
curr_p = res_30m['curr_price']

# 判斷共振
is_aligned = (res_30m['dir'] == res_60m['dir'] == res_1d['dir']) and (res_30m['dir'] != '盤整')

col_rec, col_pnl = st.columns([2, 1])

with col_rec:
    if is_aligned:
        st.success(f"🔥 **共振達成！建議執行：{opt['type']}**")
        st.write(f"👉 **建議履約價：{opt['strike']}**")
        st.write(f"👉 **參考價格**：目前指數 {curr_p:,.0f}，建議成交點數在 120~180 點之間。")
    else:
        st.warning("⚪ **目前方向不一致，建議空手觀望。**")
        st.write("上班族資金有限，僅在三框共振（30M/60M/日線全同步）時才出手。")

with col_pnl:
    if entry_idx > 0:
        pnl = service.track_option_pnl(entry_idx, curr_p, opt['type'], opt['delta_est'])
        st.metric("即時預估損益 (TWD)", f"{pnl:+,}", delta=f"{((pnl/(entry_cost*50))*100 if entry_cost>0 else 0):.1f}%")
        st.caption("註：此為 Delta 估算值，實際價格受波動率影響。")



# 2. 數據細節
st.divider()
st.subheader("🛰️ 時框狀態詳情")
c1, c2, c3 = st.columns(3)
def show_box(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.write(f"**{title}**")
        st.markdown(f"<h2 style='color:{color}'>{res['dir']}</h2>", unsafe_allow_html=True)
        st.caption(f"波動(ATR): {res['atr_val']:.1f}")

show_box(c1, "30M (進場參考)", res_30m)
show_box(c2, "60M (趨勢確認)", res_60m)
show_box(c3, "1D (大方向)", res_1d)

# 3. 策略說明書
with st.expander("📖 上班族選擇權操作守則"):
    st.markdown("""
    1. **資金分配**：$30,000 資金，建議每次僅動用 $10,000 (約 1-2 口)，保留兩次攤平或下次進場的機會。
    2. **不盯盤設定**：進場後，若 30M 訊號轉向『盤整』或『反向』，請在手機 APP 直接平倉。
    3. **停損建議**：買方權利金損失 50% 必須離場，切勿持有到歸零。
    4. **獲利目標**：選擇權具備槓桿，若獲利達 50%~100% 建議先出一半落袋為安。
    """)
