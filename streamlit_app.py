import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from app.strategy import SignalService

st.set_page_config(page_title="My-Futures 實戰監控", layout="wide")
service = SignalService()

# --- 側邊欄參數設定 ---
with st.sidebar:
    st.header("⚙️ 實戰參數設定")
    capital_val = st.number_input("起始資金 (萬元)", value=100)
    capital = capital_val * 10000
    
    st.divider()
    stop_loss_pct = st.slider("固定停損門檻 (%)", 0.5, 10.0, 2.0, step=0.5) / 100
    trailing_pct = st.slider("追蹤停利門檻 (%)", 0.5, 5.0, 1.5, step=0.1) / 100
    
    st.divider()
    st.info("### 🛠️ 停損停利建議")
    # 根據 30M 的 ATR 給予建議
    st.write("- **波動守則**：若目前 ATR 較高，建議停損設為 **3%** 以上，避免被洗出場。")
    st.write("- **波段守則**：追蹤停利設為 ATR 的 2 倍（約 **1.5% - 2%**）能有效鎖住利潤。")

st.title("🏹 My-Futures：多時框共振與實戰監控")

# 1. 資料抓取
with st.spinner("同步 30M/60M/1D 數據中..."):
    df_30m = service.fetch_data("30m", "60d")
    df_60m = service.fetch_data("60m", "60d")
    df_1d = service.fetch_data("1d", "2y")
    res_30m = service.compute_indicators(df_30m)
    res_60m = service.compute_indicators(df_60m)
    res_1d = service.compute_indicators(df_1d)

# 2. 即時監控看板
st.subheader("🛰️ 即時多時框監控")
c1, c2, c3 = st.columns(3)

def display_gauge(col, title, res):
    with col:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "gray"
        st.markdown(f"### {title}")
        st.markdown(f"<h2 style='color:{color}'>{res['dir']} ({res['prob']}%)</h2>", unsafe_allow_html=True)
        st.progress(res['prob'] / 100)
        st.caption(f"波動過濾：{'✅ 通過' if res['vol_ok'] else '❌ 波動過小'}")
        st.caption(f"當前 ATR：{res['atr_val']:.1f} 點")

display_gauge(c1, "30分K (極短線)", res_30m)
display_gauge(c2, "60分K (短線)", res_60m)
display_gauge(c3, "日K (趨勢)", res_1d)

# 3. 綜合分析報告
st.divider()
all_dirs = [res_30m['dir'], res_60m['dir'], res_1d['dir']]
is_resonance = len(set(all_dirs)) == 1

col_report, col_action = st.columns([2, 1])
with col_report:
    st.subheader("📝 策略分析報告")
    if is_resonance:
        st.success(f"🔥 **三框共振確認**：30M/60M/1D 均指向『{all_dirs[0]}』方。趨勢力道強勁。")
    else:
        st.warning(f"⚠️ **趨勢不一**：目前各時框方向分歧 {all_dirs}，不建議重倉。")
    
    st.write(f"- **平均強度**：{sum([res_30m['prob'], res_60m['prob'], res_1d['prob']])/3:.1f}%")
    st.write(f"- **進場環境**：{'波動率達標，適合趨勢策略。' if res_30m['vol_ok'] else '市場處於橫盤縮頭，建議觀望。'}")

with col_action:
    st.subheader("🎯 操作建議")
    if is_resonance and res_30m['vol_ok']:
        btn_label = f"🟢 建議做多" if all_dirs[0] == "多" else f"🔴 建議放空"
        st.button(btn_label, use_container_width=True)
    else:
        st.button("⚪ 觀望 / 收手", use_container_width=True)
    st.caption(f"當前參數：停損 {stop_loss_pct*100}% / 停利 {trailing_pct*100}%")

# 4. 策略說明書
with st.expander("📖 策略邏輯說明書"):
    st.markdown("""
    ### 1. 三框共振系統
    本系統同時監控 **30M、60M、日線**。只有當大中小時框方向一致時，才代表「波段趨勢」成形。
    
    ### 2. 進場三準則
    * **EMA 趨勢**：價格需站上 EMA 12 且 EMA 12 > EMA 26 (多頭)。
    * **RSI 動能**：RSI 需大於 50 確保多方力道佔優。
    * **ATR 波動過濾**：當前波動必須大於過去 20 期平均。避免在「死魚盤」進場浪費手續費。
    
    ### 3. 出場與防護
    * **移動停利**：從進場後最高點回落一定比例即落袋為安。
    * **7天強制平倉**：避免持有跨週產生非預期風險。
    * **結算日避險**：每月第三個週三自動平倉，不參與轉倉震盪。
    """)

# 5. 回測與下載
with st.expander("📊 展開近期回測數據"):
    perf = service.run_backtest(res_30m['df'], capital, str(datetime.now()-timedelta(days=30)), str(datetime.now()), stop_loss_pct, trailing_pct)
    if perf:
        st.write(f"近期每筆期望值：{perf['expectancy']:,.0f} 元")
        csv = perf['trades'].to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載回測報告", csv, "backtest.csv")
        st.dataframe(perf['trades'], use_container_width=True)
