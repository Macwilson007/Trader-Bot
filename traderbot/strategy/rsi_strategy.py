import pandas as pd
import numpy as np


class RSIStrategy:
    def __init__(self, rsi_period=14, oversold=30, overbought=70, atr_period=14, atr_multiplier=1.2, tp_r=2.5):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.tp_r = tp_r
    
    def calculate_rsi(self, df):
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_atr(self, df):
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        
        return tr.rolling(window=self.atr_period).mean()
    
    def get_signal(self, df):
        if len(df) < self.rsi_period + 2:
            return None, None, None, None
        
        rsi = self.calculate_rsi(df)
        atr = self.calculate_atr(df)
        
        current_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        current_price = df['close'].iloc[-1]
        current_atr = atr.iloc[-1]
        
        if pd.isna(current_rsi) or pd.isna(current_atr):
            return None, None, None, None
        
        direction = None
        
        if prev_rsi < self.oversold and current_rsi >= self.oversold:
            direction = "BUY"
        elif prev_rsi > self.overbought and current_rsi <= self.overbought:
            direction = "SELL"
        
        if direction is None:
            return None, None, None, None
        
        sl_distance = current_atr * self.atr_multiplier
        tp_distance = current_atr * self.tp_r
        
        return direction, current_atr, 1.0, {
            "sl_distance": sl_distance,
            "tp1": tp_distance,
            "tp2": tp_distance
        }


if __name__ == "__main__":
    print("RSI Strategy loaded")
    strategy = RSIStrategy()
    print("Params: RSI Period=14, Oversold=30, Overbought=70, ATR SL=1.2x, TP=2.5R")
