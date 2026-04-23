import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費
        self.tax_rate = 0.00002
        self.slippage = 2          # 單邊滑價補償
        self.initial_margin = 20000 # 預估保證金

    def _is_expiry_day(self, dt):
        """判斷是否為台指期結算日 (每月第三個週三)"""
        # 找到該月 1 號
        first_day = datetime(dt.year, dt.month, 1)
        # 找到第一個週三 (weekday: 0=Mon, 2=Wed)
        first_wed = first_day + timedelta(days=(2 - first_day.weekday() + 7) % 7)
        third_wed = first_wed + timedelta(weeks=2)
        return dt.date() == third_wed.date()

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        # 趨勢與 RSI
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        # ATR 波動率過濾器
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean() # ATR 的均線
        df['vol_ok'] = df['atr'] > df['atr_ma'] # 只有波動高於平均才進場
        
        last = df.iloc[-1]
        score = 0
        if last['close'] > last['ema_f']: score += 35
        if last['ema_f'] > last['ema_s']: score += 35
        if last['vol_ok']: score += 30 # 波動率加分
        
        direction = "多" if score >= 70 else "空" if score <= 30 else "觀望"
        return {"dir": direction, "prob": score, "df": df}

    def run_backtest(self, df, capital, start, end, stop_loss, trailing):
        df = df.loc[start:end].copy()
        if 'ema_f' not in df.columns:
            df = self.compute_indicators(df)['df']
            
        trades = []
        equity = capital
        in_pos, entry_p, entry_d, max_p = False, 0, None, 0
        
        for i in range(len(df)):
            p, d = float(df['close'].iloc[i]), df.index[i]
            is_exp = self._is_expiry_day(d)
            
            if not in_pos:
                #
