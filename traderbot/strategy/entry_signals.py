import pandas as pd
import numpy as np
from config import STRATEGY_CONFIG


class MathRiskV3Signals:
    def __init__(self):
        self.adx_period = STRATEGY_CONFIG["adx_period"]
        self.adx_min = STRATEGY_CONFIG["adx_min"]
        self.ema_trend_period = STRATEGY_CONFIG["ema_trend"]
        self.ema_entry_period = STRATEGY_CONFIG["ema_entry"]
        self.atr_period = STRATEGY_CONFIG["atr_period"]
        self.atr_multiplier = STRATEGY_CONFIG["atr_multiplier"]
        self.atr_vol_threshold = STRATEGY_CONFIG["atr_volatility_threshold"]
        self.tp1_r = STRATEGY_CONFIG["tp1_r"]
        self.tp2_r = STRATEGY_CONFIG["tp2_r"]
    
    def calculate_adx(self, df):
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(window=self.atr_period).mean()
        
        plus_di = 100 * (plus_dm.rolling(window=self.adx_period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=self.adx_period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=self.adx_period).mean()
        
        return adx, atr
    
    def calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
    
    def get_signal(self, df):
        if len(df) < 250:
            return None, None, None, None
        
        lookback = df.copy()
        
        adx, atr = self.calculate_adx(lookback)
        ema200 = self.calculate_ema(lookback['close'], self.ema_trend_period)
        ema20 = self.calculate_ema(lookback['close'], self.ema_entry_period)
        
        current_adx = adx.iloc[-1]
        current_price = lookback['close'].iloc[-1]
        current_ema200 = ema200.iloc[-1]
        current_ema20 = ema20.iloc[-1]
        current_atr = atr.iloc[-1]
        
        mean_atr = atr.tail(20).mean()
        atr_ratio = current_atr / mean_atr if mean_atr > 0 else 1
        
        if atr_ratio > self.atr_vol_threshold:
            return None, None, None, None
        
        if current_adx > self.adx_min:
            if current_price > current_ema200:
                direction = "BUY"
            elif current_price < current_ema200:
                direction = "SELL"
            else:
                return None, None, None, None
        else:
            return None, None, None, None
        
        prev_close = lookback['close'].iloc[-2]
        prev_ema20 = ema20.iloc[-2]
        
        if direction == "BUY" and prev_close < prev_ema20 and current_price > current_ema20:
            entry_signal = True
        elif direction == "SELL" and prev_close > prev_ema20 and current_price < current_ema20:
            entry_signal = True
        else:
            return None, None, None, None
        
        sl_distance = current_atr * self.atr_multiplier
        tp1 = current_atr * self.tp1_r
        tp2 = current_atr * self.tp2_r
        
        return direction, current_atr, atr_ratio, {
            "sl_distance": sl_distance,
            "tp1": tp1,
            "tp2": tp2
        }


class RiskCalculator:
    def __init__(self, account_balance):
        self.balance = account_balance
        self.risk_percent = STRATEGY_CONFIG["risk_percent"]
        self.pip_value = STRATEGY_CONFIG["pip_value"]
    
    def calculate_lot_size(self, atr, sl_distance):
        risk_amount = self.balance * self.risk_percent
        
        if self.pip_value == 1.0: # Crypto Mode
            lot_size = risk_amount / sl_distance
        else: # Forex/MT5 Mode
            sl_dollars = sl_distance * 100 * self.pip_value
            lot_size = risk_amount / sl_dollars
            
        if sl_distance <= 0:
            return 0.01
            
        return max(min(lot_size, 1.0), 0.01)
    
    def update_balance(self, new_balance):
        self.balance = new_balance
    
    def get_risk_amount(self):
        return self.balance * self.risk_percent


if __name__ == "__main__":
    print("MathRiskV3 Strategy loaded")
    signals = MathRiskV3Signals()
    print("Filters: ADX>25 + Price vs EMA200 + ATR Z-Score<2.5 + EMA20 Cross")
