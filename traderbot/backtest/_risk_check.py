print('=== $10 Account Risk Reality Check ===')
print()

# BTC: min 0.001 BTC, SL ~$1125
btc_risk = 0.001 * 1125
print(f'BTCUSDT: 0.001 BTC, SL risk = ${btc_risk:.2f} ({btc_risk/10*100:.0f}% of account)')
print('  -> Too risky. Need ~$113 minimum for BTC.')

# ETH: min 0.01 ETH, SL ~$60  
eth_risk = 0.01 * 60
print(f'ETHUSDT: 0.01 ETH, SL risk = ${eth_risk:.2f} ({eth_risk/10*100:.0f}% of account)')
print('  -> Too risky. Need ~$60 minimum for ETH.')

# XRP: 6.7 XRP, SL ~$0.015
xrp_risk = 6.7 * 0.015
print(f'XRPUSDT: 6.7 XRP, SL risk = ${xrp_risk:.2f} ({xrp_risk/10*100:.1f}% of account)')
print('  -> Safe! Proper 1% risk.')

# DOGE: 15.4 DOGE, SL ~$0.0065
doge_risk = 15.4 * 0.0065
print(f'DOGEUSDT: 15.4 DOGE, SL risk = ${doge_risk:.2f} ({doge_risk/10*100:.1f}% of account)')
print('  -> Safe! Proper 1% risk.')

# BNB: min 0.01 BNB, SL ~$15
bnb_risk = 0.01 * 15
print(f'BNBUSDT: 0.01 BNB, SL risk = ${bnb_risk:.2f} ({bnb_risk/10*100:.0f}% of account)')
print('  -> Borderline. Need ~$15 minimum for BNB.')

# SOL: min 0.1 SOL, SL ~$4
sol_risk = 0.1 * 4
print(f'SOLUSDT: 0.1 SOL, SL risk = ${sol_risk:.2f} ({sol_risk/10*100:.0f}% of account)')
print('  -> Too risky. Need ~$40 minimum for SOL.')

# ADA: 1.0 ADA min, SL ~$0.012
ada_risk = 1.0 * 0.012
print(f'ADAUSDT: 1.0 ADA, SL risk = ${ada_risk:.3f} ({ada_risk/10*100:.1f}% of account)')
print('  -> Safe! Well under 1% risk.')

print()
print('SAFE for a 10 dollar account: XRP, DOGE, ADA')
print('NEED 50 dollars minimum:      BNB, SOL')
print('NEED 100 dollars minimum:     BTC, ETH')
