import streamlit as st
from datetime import datetime
import pandas as pd

# 確保引用路徑與目錄結構一致
try:
    from app.strategy import SignalService
except ImportError:
    # 如果還沒建立 app 資料夾，暫時改為從根目錄引用
    from strategy import SignalService

st.set_page_config(page_title="台指期波段監控", layout="wide")
st.title("台指期動能趨勢監控（30分K / 60分K / 日K）")

# 初始化 Service
if "service" not in st.session_state:
    with st.spinner("正在初始化數據，請稍候..."):
        st.session_state.service = SignalService(symbol="^TWII")

service = st.session_state.service

# UI 按鈕與佈局
col1, col2 = st.columns([1, 3])
with col1:
    force = st.button("立即刷新數據")
with col2:
    st.caption("規則：7天強平 / 停損10% / 動態追蹤停利")

try:
    payload = service.refresh() if force else service.get_latest()
except Exception as exc:
    st.error(f"資料更新失敗：{exc}")
    st.stop()

# 顯示更新時間
updated_time = datetime.fromisoformat(payload['updated_at']).strftime('%Y-%m-%d %H:%M:%S')
st.info(f"標的：`{payload['symbol']}` | 更新時間（UTC）：{updated_time}")

# 顯示三種時框的卡片
frames = payload["timeframes"]
cols = st.columns(3)

for idx, key in enumerate(["30m", "60m", "1d"]):
    frame = frames[key]
    backtest = frame["backtest"]
    with cols[idx]:
        st.subheader(f"{key} 訊號")
        st.metric("最新訊號", frame["latest_signal"])
        st.metric("最新價格", f"{frame['latest_price']:,}")
        st.write(f"RSI: {frame['rsi']} | Momentum: {frame['momentum']}%")
        
        with st.expander("回測摘要"):
            st.write(f"總報酬：{backtest['total_return_pct']}%")
            st.write(f"勝率：{backtest['win_rate_pct']}%")
