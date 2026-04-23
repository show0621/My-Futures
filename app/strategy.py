import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class MTXEngine:
    """微台指回測引擎 (1點=50元)"""
    def __init__(self):
        self.point_value = 50  # 微台 1點 50元
        self.fee_per_side = 20  # 單邊手續費 20
        self.tax_rate = 0.00002 # 期交稅 10萬分之2

    def calculate_cost(self, price):
        # 總成本 = 手續費 + 稅
        tax = price * self.point_value * self.tax_rate
        return self.fee_per_side + tax

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.engine = MTXEngine()
        
    def get_data(self):
        # 抓取三種時框
        d_1d = yf.download(self.symbol, period="2y", interval="1d")
        d_60m = yf.download(self.symbol, period="60d", interval="60m")
        d_30m = yf.download(self.symbol, period="60d", interval="30m")
        return {"1d": d_1d, "60m": d_60m, "30m": d_30m}

    def compute_indicators(self, df):
        df = df.copy()
        # 修正 yfinance MultiIndex 問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 計算趨勢與動能
        df['ema_fast'] = df['Close'].ewm(span=12).mean()
        df['ema_slow'] = df['Close'].ewm(span=26).mean()
        df['rsi'] = self.calculate_rsi(df['Close'], 14)
        
        # 多空機率判定邏輯 (簡單示例：指標站上均線且RSI強勢)
        prob = 0
        if df['Close'].iloc[-1] > df['ema_fast'].iloc[-1]: prob += 30
        if df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1]: prob += 40
        if df['rsi'].iloc[-1] > 50: prob += 30
        
        direction = "看多" if df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1] else "看空"
        return direction, prob, df

    def calculate_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def run_backtest(self, df, stop_loss=0.1, trailing=0.05):
        """
        核心策略：7天強平 / 移動停利 / 停損
        """
        # (此處簡化回測流程，僅計算近期交易點位用於展示)
        trades = []
        # 實務上這裡會跑一個迴圈紀錄 Entry/Exit 
        # 這裡回傳模擬數據供前端渲染
        return [
            {"date": "2024-03-15", "type": "做多", "price": 20100, "reason": "三框共振看多", "pnl": 5200},
            {"date": "2024-03-22", "type": "平倉", "price": 20210, "reason": "滿7天強制平倉", "pnl": 0}
        ]
