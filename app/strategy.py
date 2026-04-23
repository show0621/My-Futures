import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費 20 元
        self.tax_rate = 0.00002    # 期交稅 0.002%
        
    def get_data(self):
        # 抓取不同長度的數據
        return {
            "1d": yf.download(self.symbol, period="2y", interval="1d"),
            "60m": yf.download(self.symbol, period="60d", interval="60m"),
            "30m": yf.download(self.symbol, period="60d", interval="30m")
        }

    def compute_indicators(self, df):
        df = df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 趨勢指標
        df['ema12'] = df['Close'].ewm(span=12).mean()
        df['ema26'] = df['Close'].ewm(span=26).mean()
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        
        # 多空機率 (0-100)
        last = df.iloc[-1]
        prob = 0
        if last['Close'] > last['ema12']: prob += 30
        if last['ema12'] > last['ema26']: prob += 40
        if last['rsi'] > 55: prob += 30
        elif last['rsi'] < 45: prob -= 30 # 減分代表看空力道
        
        direction = "多" if prob > 50 else "空" if prob < -50 else "中立"
        return {"dir": direction, "prob": abs(prob), "df": df}

    def run_backtest(self, df, stop_loss_pct=0.02, trailing_pct=0.015):
        """
        模擬交易邏輯：7天強平、移動停利、固定停損
        """
        df = df.copy()
        trades = []
        in_position = False
        entry_price = 0
        entry_date = None
        max_price_since_entry = 0
        
        for i in range(len(df)):
            price = df['Close'].iloc[i]
            date = df.index[i]
            
            # 訊號觸發 (這裡簡化為當 EMA 交叉時進場)
            if not in_position:
                if df['ema12'].iloc[i] > df['ema26'].iloc[i]:
                    in_position = True
                    entry_price = price
                    entry_date = date
                    max_price_since_entry = price
                    trades.append({"entry_date": date, "type": "做多", "entry_price": price})
            
            else:
                max_price_since_entry = max(max_price_since_entry, price)
                days_held = (date - entry_date).days
                
                # 判斷出場條件
                reason = ""
                if price < entry_price * (1 - stop_loss_pct): reason = "固定停損"
                elif price < max_price_since_entry * (1 - trailing_pct): reason = "移動停利觸發"
                elif days_held >= 7: reason = "7天強制平倉"
                
                if reason:
                    exit_price = price
                    # 計算稅費
                    cost = (entry_price + exit_price) * self.point_value * self.tax_rate + (self.fee * 2)
                    raw_pnl = (exit_price - entry_price) * self.point_value
                    net_pnl = raw_pnl - cost
                    
                    trades[-1].update({
                        "exit_date": date,
                        "exit_price": exit_price,
                        "reason": reason,
                        "net_pnl": round(net_pnl)
                    })
                    in_position = False
        
        return [t for t in trades if "exit_date" in t]
