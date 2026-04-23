import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費 20 元
        self.tax_rate = 0.00002    # 期交稅
        self.slippage = 2          # 單邊滑價補償 2 點
        self.initial_margin = 20000 # 每口預估保證金

    def _is_expiry_day(self, dt):
        """判斷是否為台指期結算日 (每月第三個週三)"""
        first_day = datetime(dt.year, dt.month, 1)
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
        # 趨勢：EMA 12 / 26
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        # 波動率過濾器：ATR (平均真實波幅)
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean()
        df['vol_ok'] = df['atr'] > df['atr_ma'] # 波動大於平均才視為有效行情
        
        last = df.iloc[-1]
        score = 0
        if last['close'] > last['ema_f']: score += 35
        if last['ema_f'] > last['ema_s']: score += 35
        if last['vol_ok']: score += 30
        
        direction = "多" if score >= 70 else "空" if score <= 30 else "觀望"
        return {"dir": direction, "prob": score, "df": df}

    def run_backtest(self, df, capital, start, end, stop_loss, trailing):
        # 確保資料包含指標
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
                # 進場：EMA金叉 + 波動足夠 + 非結算日
                if df['ema_f'].iloc[i] > df['ema_s'].iloc[i] and df['vol_ok'].iloc[i] and not is_exp:
                    in_pos, entry_p, entry_d, max_p = True, p + self.slippage, d, p
            else:
                max_p = max(max_p, p)
                reason = ""
                # 判斷出場
                if p < entry_p * (1 - stop_loss): reason = "固定停損"
                elif p < max_p * (1 - trailing): reason = "移動停利"
                elif (d - entry_d).days >= 7: reason = "7天強平"
                elif is_exp: reason = "結算日避險"
                
                if reason:
                    exit_p = p - self.slippage
                    cost = (entry_p + exit_p) * self.point_value * self.tax_rate + (self.fee * 2)
                    net = (exit_p - entry_p) * self.point_value - cost
                    trades.append({
                        "進場時間": entry_d, "出場時間": d, "原因": reason,
                        "進場價": round(entry_p), "出場價": round(exit_p), "損益": round(net)
                    })
                    equity_curve.append(equity_curve[-1] + net)
                    in_pos = False
        
        if not trades: return None
        
        tdf = pd.DataFrame(trades)
        wins = tdf[tdf['損益'] > 0]
        losses = tdf[tdf['損益'] <= 0]
        win_rate = len(wins) / len(tdf)
        avg_win = wins['損益'].mean() if not wins.empty else 0
        avg_loss = abs(losses['損益'].mean()) if not losses.empty else 1
        
        return {
            "total_pnl": tdf['損益'].sum(),
            "win_rate": win_rate,
            "expectancy": (win_rate * avg_win) - ((1 - win_rate) * avg_loss),
            "mdd": (pd.Series(equity_curve).cummax() - pd.Series(equity_curve)).max(),
            "pl_ratio": avg_win / avg_loss,
            "sharpe": (tdf['損益'].mean() / tdf['損益'].std() * np.sqrt(252)) if len(tdf) > 1 else 0,
            "trades": tdf
        }
