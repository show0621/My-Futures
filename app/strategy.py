import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費
        self.tax_rate = 0.00002    # 期交稅
        self.initial_margin = 20000 # 微台初始保證金(估算)

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=12).mean()
        df['ema_slow'] = df['close'].ewm(span=26).mean()
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50)
        
        last = df.iloc[-1]
        score = 0
        if last['close'] > last['ema_fast']: score += 35
        if last['ema_fast'] > last['ema_slow']: score += 35
        if last['rsi'] > 50: score += 30
        direction = "多" if score >= 70 else "空" if score <= 30 else "盤整"
        return {"dir": direction, "prob": score, "df": df}

    def run_backtest(self, df, initial_capital, stop_loss_pct=0.02, trailing_pct=0.015):
        if 'ema_fast' not in df.columns:
            df = self.compute_indicators(df)['df']
            
        trades = []
        equity_curve = [initial_capital]
        in_pos = False
        entry_p, entry_d, max_p = 0, None, 0
        
        for i in range(len(df)):
            p = float(df['close'].iloc[i])
            d = df.index[i]
            
            if not in_pos:
                if df['ema_fast'].iloc[i] > df['ema_slow'].iloc[i]:
                    in_pos, entry_p, entry_d, max_p = True, p, d, p
            else:
                max_p = max(max_p, p)
                days = (d - entry_d).days
                reason = ""
                if p < entry_p * (1 - stop_loss_pct): reason = "固定停損"
                elif p < max_p * (1 - trailing_pct): reason = "移動停利"
                elif days >= 7: reason = "7天強平"
                
                if reason:
                    cost = (entry_p + p) * self.point_value * self.tax_rate + (self.fee * 2)
                    net_pnl = (p - entry_p) * self.point_value - cost
                    trades.append({
                        "exit_date": d,
                        "pnl": net_pnl,
                        "ret": net_pnl / initial_capital,
                        "reason": reason
                    })
                    equity_curve.append(equity_curve[-1] + net_pnl)
                    in_pos = False
                    
        # 計算績效指標
        if not trades: return None
        
        tdf = pd.DataFrame(trades)
        wins = tdf[tdf['pnl'] > 0]
        losses = tdf[tdf['pnl'] <= 0]
        
        win_rate = len(wins) / len(tdf)
        avg_win = wins['pnl'].mean() if not wins.empty else 0
        avg_loss = abs(losses['pnl'].mean()) if not losses.empty else 1
        
        # 績效摘要
        summary = {
            "total_pnl": tdf['pnl'].sum(),
            "max_ret": tdf['ret'].max(),
            "avg_ret": tdf['ret'].mean(),
            "win_rate": win_rate,
            "profit_loss_ratio": avg_win / avg_loss,
            "expectancy": (win_rate * avg_win) - ((1 - win_rate) * avg_loss),
            "mdd": (pd.Series(equity_curve).cummax() - pd.Series(equity_curve)).max(),
            "sharpe": (tdf['ret'].mean() / tdf['ret'].std() * np.sqrt(252)) if len(tdf) > 1 else 0,
            "trades": tdf
        }
        return summary
