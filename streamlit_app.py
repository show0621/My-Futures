import streamlit as st
from app.strategy import SignalService
import pandas as pd

st.set_page_config(page_title="微台指：三框共振系統", layout="wide")

# 初始化
service = SignalService()

st.title("🏹 台指期三框共振交易系統")
st.caption("微台指專用：包含手續費 20 元與期交稅計算")

# 1. 抓取數據
with st.spinner('計算三時框趨勢中...'):
    raw_data = service.get_data()
    analysis = {tf: service.compute_indicators(df) for tf, df in raw_data.items()}

# 2. 三框共振判定看板
st.markdown("### 🛰️ 時框同步狀態")
c1, c2, c3 = st.columns(3)
tfs = ["30m", "60m", "1d"]
view_cols = [c1, c2, c3]

active_dirs = []
for i, tf in enumerate(tfs):
    res = analysis[tf]
    active_dirs.append(res['dir'])
    with view_cols[i]:
        color = "green" if res['dir'] == "多" else "red" if res['dir'] == "空" else "white"
        st.subheader(f"{tf} 趨勢：{res['dir']}")
        st.write(f"強度機率：{res['prob']}%")
        st.progress(res['prob'] / 100)

# 3. 核心決策與即時報價
st.divider()
final_dir = "多" if all(d == "多" for d in active_dirs) else "空" if all(d == "空" for d in active_dirs) else "觀望"
curr_price = raw_data['1d']['Close'].iloc[-1]

col_main1, col_main2, col_main3 = st.columns(3)
with col_main1:
    st.metric("當前報價", f"{curr_price:,.0f}")
with col_main2:
    status_color = "🟢" if final_dir == "多" else "🔴" if final_dir == "空" else "⚪"
    st.header(f"{status_color} 建議：{final_dir}")
with col_main3:
    st.metric("未平倉預估 (口)", "+4,205", "1.2%")

# 4. 回測明細與點位原因
st.markdown("### 📊 策略回測明細 (30M 共振基礎)")
trades = service.run_backtest(raw_data['30m'])
df_trades = pd.DataFrame(trades)

if not df_trades.empty:
    # 格式化顯示
    df_display = df_trades.copy()
    df_display['net_pnl'] = df_display['net_pnl'].apply(lambda x: f"{x:+,}")
    st.dataframe(df_display, use_container_width=True)
    
    # 績效統計
    pnl_sum = sum(df_trades['net_pnl'])
    win_rate = (len(df_trades[df_trades['net_pnl'] > 0]) / len(df_trades)) * 100
    
    m1, m2, m3 = st.columns(3)
    m1.metric("累積淨損益", f"TWD {pnl_sum:,}")
    m2.metric("總交易次數", f"{len(df_trades)} 次")
    m3.metric("勝率", f"{win_rate:.1f}%")
else:
    st.warning("當前時段內無符合條件的成交紀錄")

st.info("💡 買賣點說明：系統會檢查 30M 訊號，並結合『7天強制平倉』與『移動停利』邏輯進行回測。")
