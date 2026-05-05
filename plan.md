# TraderBot Project Plan

## Project Overview
Automated trading bot for MetaTrader 5 using multi-strategy approach.

---

## Phase 1: Strategy Implementation (Completed)

### Strategy Assignments
| Symbol | Strategy | Backtest Results (1 Year H1) |
|--------|----------|----------------------------|
| XAUUSD | MathRiskV3 | Win Rate: 52.1%, PF: 2.12, Profit: $6,620 |
| EURUSD | RSI | Win Rate: 43.5%, PF: 1.54, Profit: $4,094 |
| GBPUSD | EMA Cross | Win Rate: 40.3%, PF: 1.32, Profit: $1,171 |

### Files Created
- `traderbot/strategy/rsi_strategy.py` - RSI mean reversion for EURUSD
- `traderbot/strategy/ema_crossover.py` - EMA crossover for GBPUSD
- `traderbot/strategy/entry_signals.py` - MathRiskV3 for XAUUSD

---

## Phase 2: Installer Development (Pending)

### Objective
Create a standalone Windows installer that allows users to:
1. Enter their MT5 credentials
2. Auto-install MT5 if missing
3. Configure bot settings
4. Run the bot on their system

### Project Structure
```
TraderBot/
├── installer/                    # Installer folder
│   ├── setup_ui.py              # GUI for user credentials
│   ├── mt5_checker.py           # Check/install MT5
│   ├── config_writer.py         # Generate user config
│   ├── requirements.txt         # Installer dependencies
│   └── installer.iss           # Inno Setup script
├── traderbot/
│   ├── strategy/
│   ├── config.py                # Reads from user data
│   └── ...
├── logs/
└── start_bot.bat
```

### Components

#### 1. setup_ui.py
- GUI window using tkinter
- Fields:
  - MT5 Login ID
  - MT5 Password
  - MT5 Server
  - Initial Balance
  - Risk Percentage
- "Install & Launch" button

#### 2. mt5_checker.py
- Check default MT5 installation paths:
  - `C:\Program Files\MetaTrader 5\terminal64.exe`
  - `C:\Program Files (x86)\MetaTrader 5\terminal.exe`
- If not found, download from MetaQuotes
- Silent installation option

#### 3. config_writer.py
- Generate encrypted `user_config.json`
- Store in `%APPDATA%\TraderBot\`
- Encrypt credentials using Fernet

#### 4. run_bot.py
- Launcher script
- Reads user config
- Starts main bot

### Tools Required
| Tool | Purpose |
|------|---------|
| Inno Setup | Create Windows installer .exe |
| PyInstaller | Package Python scripts |
| tkinter | Installer GUI (built-in) |
| requests | Download MT5 |
| cryptography | Encrypt credentials |

### Installer Features
- Modern GUI installer
- MT5 auto-detection and download
- Python dependency installation
- Desktop shortcut creation
- Settings persistence
- Both local and online distribution

### Distribution Options
- Local network installation
- Online download (website hosting)

---

## Phase 3: Current Issues (Pending)

### Issue: EURUSD and GBPUSD Not Trading
- Status: Investigating
- Bot connects and logs correctly
- All 3 symbols detected
- Only XAUUSD trading expected at scheduled times

---

## Phase 4: Future Enhancements (Backlog)

### Potential Additions
- [ ] More forex pairs (AUDUSD, USDJPY, etc.)
- [ ] Additional strategies (MACD, Stochastic)
- [ ] Web dashboard for monitoring
- [ ] Trade notifications (Telegram/Email)
- [ ] Performance analytics
- [ ] Multi-timeframe analysis
- [ ] News event filtering
- [ ] Correlation-based position sizing

### Broker Compatibility
- [ ] Test on other MT5 brokers
- [ ] Support for cTrader
- [ ] Support for cAlgo

---

## Configuration Reference

### Trading Sessions (WAT - UTC+1)
| Session | Time |
|---------|------|
| London Overlap | 08:00 |
| London AM | 09:00 |
| London PM | 13:00 |
| NY AM | 14:00 |
| NY PM | 15:00 |

### Strategy Parameters

#### RSI Strategy (EURUSD)
- Period: 14
- Oversold: 25
- Overbought: 75
- SL: ATR × 1.5
- TP: ATR × 2.0

#### EMA Cross Strategy (GBPUSD)
- Fast EMA: 20
- Slow EMA: 50
- SL: ATR × 1.5
- TP: ATR × 2.0

#### MathRiskV3 (XAUUSD)
- ADX Min: 20
- EMA Trend: 200
- EMA Entry: 20
- ATR Volatility Threshold: 3.0
- SL: ATR × 1.5
- TP1: ATR × 1.5
- TP2: ATR × 2.0

---

## File Inventory

```
TraderBot/
├── logs/
│   └── trading.log
├── traderbot/
│   ├── __pycache__/
│   ├── backtest/
│   │   ├── counter_trend_v3.py
│   │   ├── forex_strategies.py
│   │   ├── full_backtest_all_pairs.py
│   │   ├── math_risk_v3.py
│   │   ├── mtf_session_strategy.py
│   │   └── parameter_optimizer.py
│   ├── connector/
│   │   └── mt5_connector.py
│   ├── core/
│   │   └── session_manager.py
│   ├── execution/
│   │   └── order_manager.py
│   ├── logs/
│   ├── strategy/
│   │   ├── ema_crossover.py
│   │   ├── entry_signals.py
│   │   └── rsi_strategy.py
│   ├── bot.py
│   └── config.py
├── requirements.txt
└── start_bot.bat
```

---

## Installation for Development

```bash
# Clone repo
git clone <repo_url>
cd TraderBot

# Install dependencies
pip install -r requirements.txt

# Run bot
py traderbot/bot.py
# or
start_bot.bat
```
