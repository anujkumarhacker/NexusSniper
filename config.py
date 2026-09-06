"""
NexusSniper (NP) - Master Configuration Matrix
Unified quantitative risk, trailing tripwires, and API parameter definitions.
"""
import sys

# --- BINANCE TESTNET API CREDENTIALS ---
try:
    from app_credentials import BINANCE_API_KEY, BINANCE_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    print("\033[1;91m❌ CRITICAL: 'app_credentials.py' not found. Please create it using app_credentials.py.example.\033[0m")
    sys.exit(1)

if any(not val or "YOUR_" in str(val) for val in [BINANCE_API_KEY, BINANCE_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    print("\033[1;91m❌ CRITICAL: Placeholder credentials detected. Please update 'app_credentials.py' with real keys.\033[0m")
    sys.exit(1)

API_KEY = BINANCE_API_KEY
API_SECRET = BINANCE_API_SECRET

# --- TELEGRAM ALERTS CONFIGURATION ---
ENABLE_TELEGRAM = True

# --- ENVIRONMENT SELECTION ---
USE_TESTNET = True             # True routes to testnet.binancefuture.com
BASE_QUOTE = "USDT"

# --- UNIVERSE SELECTION & S3 SCREENER ---
MIN_24H_QUOTE_VOLUME = 500_000_000  # $500M 24h volume threshold (with dynamic testnet fallback)
TOP_PAIRS_COUNT = 20                # 10 Long relative strength + 10 Short relative strength
REBALANCE_INTERVAL_MINS = 15        # Universe recalculation frequency

# Static Fallback Watchlist (Used only if exchange API fails entirely)
WATCHLIST = [
    "ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "LINKUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"
]

# --- PORTFOLIO HEAT & CAPITAL GOVERNORS ---
INITIAL_CAPITAL = 5000.0            # Used for baseline HWM tracking
RISK_PER_TRADE_PCT = 0.01          # 1% dynamic risk per trade (No heatmap decay)
MAX_CONCURRENT_POSITIONS = 10       # Global portfolio capacity
MAX_DIRECTIONAL_POSITIONS = 10      # Max concurrent Longs or Shorts
DEFAULT_LEVERAGE = 10               # Target leverage (auto-capped by pair tier)
MARGIN_MODE = "ISOLATED"

# --- INSTITUTIONAL CIRCUIT BREAKERS ---
MAX_DAILY_DRAWDOWN_PCT = 0.10       # 10% daily loss limit (Midnight UTC roll)
MAX_HWM_DRAWDOWN_PCT = 0.20         # 20% drop from All-Time High Water Mark
MAX_CONSECUTIVE_LOSSES = 10         # 10 consecutive stop-outs triggers 48h halt
CIRCUIT_BREAKER_LOCKOUT_HOURS = 48  # Cooldown window to let toxic chop pass

# --- SMC STRATEGY PARAMETERS (NLE CORE) ---
TIMEFRAME_MACRO = "1h"
TIMEFRAME_SETUP = "15m"
TIMEFRAME_ENTRY = "1m"

ER_PERIOD = 14                      # Kaufman Efficiency Ratio lookback
ER_TREND_THRESHOLD = 0.25           # Market regime floor (ER >= 0.25 required)
SWEEP_MIN_DEPTH_PCT = 0.0008        # 0.08% minimum penetration beyond 15m fractal
FRACTAL_WINDOW = 3                  # Fractal detection window (n=3)

# --- GTC ENTRY ORDER LIFESPAN MATRIX ---
GTC_MAX_AGE_SECONDS = 3600          # 60-minute time decay cancellation
GTC_RUNAWAY_R_MULTIPLE = 5.0        # Cancel entry if price expands to 5R without fill

# --- ASYMMETRIC 6-TIER TRAILING RATCHET (1:28 RRR) ---
BE_TRIGGER_R = 2.5                  # At +2.5R, drop SL to Breakeven (+0.04% buffer)
RATCHET_1_TRIGGER_R = 5.0           # At +5.0R, lock +2.5R
RATCHET_1_LOCK_R = 2.5
RATCHET_2_TRIGGER_R = 10.0          # At +10.0R, lock +7.0R
RATCHET_2_LOCK_R = 7.0
RATCHET_3_TRIGGER_R = 15.0          # At +15.0R, drop SL to +12.0R
RATCHET_3_LOCK_R = 12.0
RATCHET_4_TRIGGER_R = 20.0          # At +20.0R, drop SL to +17.0R
RATCHET_4_LOCK_R = 17.0
TERMINAL_TP_R = 28.0                # Final limit exit target

# --- EXCHANGE FRICTION ESTIMATIONS (FALLBACKS) ---
LIMIT_FILL_BUFFER_PCT = 0.0002      # 0.02% queue penetration threshold
MAKER_FEE_PCT = 0.0002
TAKER_FEE_PCT = 0.0005
MAINTENANCE_MARGIN_RATE = 0.004     # 0.4% default MMR
