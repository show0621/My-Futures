import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import os

st.set_page_config(page_title="台指選擇權波段策略", layout="wide")

@st.cache_data
def load_data():
    file_path = "data/txf_options_backtest.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        return df
    return pd.DataFrame()

df = load_data()

st.title("📈 台指選擇權 60K 波段自動回測系統")

if df.empty:
    st.warning("⚠️ 尚未找到資料，請先執行 `update_data.py` 更新數據，或等待 GitHub Actions 執行。")
else:
    # -------------------------
    # 1. 計算核心績效指標
    # -------------------------
    # 濾出有實際交易的紀錄
    trades = df[df['Signal'] != 0].copy()
    trade_results = trades['Options_Profit_TWD'].dropna()
    
    if len(trade_results) > 0:
        win_rate = (len(trade_results[trade_results > 0]) / len(trade_results)) * 100
        ev = trade_results.mean()
        # 夏普值計算 (假設無風險利率近似於 0，並以交易頻率年化)
        std_dev = trade_results.std()
        sharpe = (ev / std_dev) * np.sqrt(252) if std_dev != 0 else 0
    else:
        win_rate = ev = sharpe = 0

    # -------------------------
    # 2. 顯示指標面板
    # -------------------------
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總交易次數", f"{len(trade_results)} 次")
    col2.metric("策略勝率", f"{win_rate:.2f}%")
    col3.metric("單筆期望值", f"NT$ {ev:.0f}")
    col4.metric("策略夏普值", f"{sharpe:.2f}")

    # -------------------------
    # 3. 繪製互動式 K 線圖
    # -------------------------
    # 為了圖表效能，預設顯示最後 300 根 K 線
    plot_df = df.tail(300)
    
    fig = go.Figure(data=[go.Candlestick(x=plot_df.index,
                    open=plot_df['Open'], high=plot_df['High'],
                    low=plot_df['Low'], close=plot_df['Close'], name="台指 60K")])

    # 標示買點 (做多 Call)
    buy_signals = plot_df[plot_df['Signal'] == 1]
    fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] - 50,
                             mode='markers+text', marker=dict(symbol='triangle-up', color='red', size=12),
                             name='買進 Call', text=buy_signals['Position_Size'].astype(int).astype(str) + " 口",
                             textposition="bottom center"))

    # 標示賣點 (買進 Put)
    sell_signals = plot_df[plot_df['Signal'] == -1]
    fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] + 50,
                             mode='markers+text', marker=dict(symbol='triangle-down', color='green', size=12),
                             name='買進 Put', text=sell_signals['Position_Size'].astype(int).astype(str) + " 口",
                             textposition="top center"))

    fig.update_layout(height=650, title="最近 300 小時 K 線與進出場點位", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # -------------------------
    # 4. 交易明細清單與 CSV 下載
    # -------------------------
    st.subheader("📋 交易紀錄與詳細說明")
    st.markdown("""
    **選擇權策略評估說明：**
    純做買方（Long Call / Long Put）的最佳策略通常是買進 **價平 (ATM)** 或 **價外一檔 (OTM)** 的合約。
    - 買太深價外 (Deep OTM) 雖然權利金便宜，但勝率極低，且 Gamma 爆發力需要極大行情才能體現。
    - 買價內 (ITM) 成本過高，失去了買方「以小搏大」的槓桿優勢。
    此回測系統已透過 `預期點數 × 0.5 (價平Delta) × 50元` 來模擬最適策略的損益。
    """)
    
    display_cols = ['Close', 'ATR', 'Signal', 'Position_Size', 'Trade_Profit_Points', 'Options_Profit_TWD']
    st.dataframe(trades[display_cols].sort_index(ascending=False).style.format({
        'Close': '{:.0f}', 'ATR': '{:.2f}', 'Trade_Profit_Points': '{:.0f}', 'Options_Profit_TWD': '{:.0f}'
    }))

    # 提供 CSV 下載 (加入 utf-8-sig 以避免 Excel 開啟中文亂碼)
    csv = df.to_csv().encode('utf-8-sig')
    st.download_button(
        label="📥 下載完整歷史回測 CSV 資料",
        data=csv,
        file_name='txf_options_full_backtest.csv',
        mime='text/csv',
    )
