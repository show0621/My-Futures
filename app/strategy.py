import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      
        self.fee = 20              
        self.tax_rate = 0.00002    
        self.slippage = 2          
        self.initial_margin = 20000 

    def _is_expiry_day(self, dt):
        dt_naive = dt.replace(tzinfo=None)
        first_day = datetime(dt_naive.year, dt_naive.month, 1)
        first_wed = first_day + timedelta(days=(2 - first_day.weekday() + 7) % 7)
        third_wed = first_wed + timedelta(weeks=2)
        return dt_naive.date() == third_wed.date()

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        # ATR 波動過濾
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean()
        df['vol_ok'] = df['atr'] > df['atr_ma']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, np.nan))))
        df['rsi'] = df['rsi'].fillna(50)
        
        last = df.iloc[-1]
        long_prob, short_prob = 0, 0
        
        if last['close'] > last['ema_f']: long_prob += 35
        if last['ema_f'] > last['ema_s']: long_prob += 35
        if last['rsi'] > 50: long_prob += 30
        
        if last['close'] < last['ema_f']: short_prob += 35
        if last['ema_f'] < last['ema_s']: short_prob += 35
        if last['rsi'] < 50: short_prob += 30
        
        prob = long_prob if long_prob >= short_prob else short_prob
        direction = "多" if long_prob > short_prob else "空"
        if abs(long_prob - short_prob) < 20: direction = "盤整"
        
        return {"dir": direction, "prob": prob, "df": df, "vol_ok": last['vol_ok'], "atr_val": last['atr']}

    def run_backtest(self, df, capital, start, end, stop_loss, trailing):
        if 'ema_f' not in df.columns:
            df = self.compute_indicators(df)['df']
        df = df.loc[start:end].copy()
        if df.empty: return None
        trades = []
        equity_curve = [capital]
        in_pos, entry_p, entry_d, max_p = False, 0, None, 0
        for i in range(len(df)):
            p, d = float(df['close'].iloc[i]), df.index[i]
            is_exp = self._is_expiry_day(d)
            if not in_pos:
                if df['ema_f'].iloc[i] > df['ema_s'].iloc[i] and df['vol_ok'].iloc[i] and not is_exp:
                    in_pos, entry_p, entry_d, max_p = True, p + self.slippage, d, p
            else:
                max_p = max(max_p, p)
                reason = ""
                if p < entry_p * (1 - stop_loss): reason = "固定停損"
                elif p < max_p * (1 - trailing): reason = "移動停利"
                elif (d - entry_d).days >= 7: reason = "7天強平"
                elif is_exp: reason = "結算日避險"
                if reason:
                    exit_p = p - self.slippage
                    cost = (entry_p + exit_p) * self.point_value * self.tax_rate + (self.fee * 2)
                    net = (exit_p - entry_p) * self.point_value - cost
                    trades.append({"進場時間": entry_d, "出場時間": d, "原因": reason, "進場價": round(entry_p), "出場價": round(exit_p), "損益": round(net)})
                    equity_curve.append(equity_curve[-1] + net)
                    in_pos = False
        if not trades: return None
        tdf = pd.DataFrame(trades)
        wins = tdf[tdf['損益'] > 0]
        return {"total_pnl": tdf['損益'].sum(), "expectancy": (len(wins)/len(tdf)*wins['損益'].mean()) - (len(tdf[tdf['損益']<=0])/len(tdf)*abs(tdf[tdf['損益']<=0]['損益'].mean())), "trades": tdf}
