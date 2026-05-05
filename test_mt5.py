import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

print("Initializing MT5...")
if not mt5.initialize():
    print("Initialize failed, error code =", mt5.last_error())
    quit()

print("Logging in...")
authorized = mt5.login(login=221229, password="Q$8SGx5U", server="CXMDirect-Demo")
if authorized:
    print("Login successful")
    symbol = "EURUSDc"
    print(f"Fetching data for {symbol}...")
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 10)
    if rates is not None:
        print(f"Successfully fetched {len(rates)} bars")
        print(pd.DataFrame(rates))
    else:
        print("Failed to fetch rates, error =", mt5.last_error())
else:
    print("Login failed, error code =", mt5.last_error())

mt5.shutdown()
