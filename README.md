# NexusSniper (NP) ⚡

An institutional-grade, asynchronous algorithmic trading engine built for Binance USD(S)-M Futures. NexusSniper combines the Smart Money Concepts (SMC) quantitative edge of the **Nexus Liquidity Engine (NLE)** with the execution mechanics of **CryptoSniper (CS)** and the low-bandwidth monitoring interface of **LiquidityPulse (LP)**.

---

## Architectural Pillars

1. **Network Mesh (`network_mesh.py`):**
   - Native CCXT WebSocket streams for sub-second tick and candle ingestion.
   - Transparent, automatic fallback to REST API if WebSocket streams encounter disconnects.

2. **Quantitative SMC Engine (`smc_engine.py`):**
   - **1h Macro Regime Filter:** Uses Kaufman Efficiency Ratio (ER >= 0.25) to reject consolidations and toxic chop.
   - **15m Tactical Sweeps:** Detects Turtle Soup penetration (>= 0.08%) of fractal liquidity pools.
   - **1m Precision Entry:** Maps Fair Value Gap (FVG) proximal edges for GTC limit order entries.

3. **Risk & Margin Governor (`risk_governor.py`):**
   - **Dynamic Free Margin Verification:** Slices trades to fit available free margin and exchange-specific leverage tiers (e.g., 5x, 10x).
   - **10% Daily Drawdown Breaker:** Freezes new entries until the 00:00 UTC rollover if equity drops 10%.
   - **20% Peak HWM Breaker:** Halts trading if equity retreats 20% from its all-time high-water mark.
   - **10 Consecutive Loss Breaker:** Locks out new entries for 48 hours to protect capital during persistent adverse market conditions.

4. **Layered Safety Net & Orphan Sweeper (`execution_router.py`):**
   - **Dynamic GTC Expiry Matrix:** Cancels unfilled GTC entries if time decays (> 60m), price breaks invalidation extremes, price runs to 5R without a fill, or 1h ER degrades.
   - **Layered Trailing Safety Net:** Ratchets stops across 6 tiers (+2.5R Breakeven, +5R, +10R, +15R, +20R, +28R TP) without canceling previous stops, catching violent wick slippage.
   - **Orphan Sweeper:** Cleans up all residual safety-net orders immediately upon trade resolution.

5. **Telemetry & C2 Interface (`web_dashboard.py`):**
   - Dark-mode dashboard displaying 8 primary KPI cards.
   - One-click "Copy Positions" and "Copy System Log" clipboard integrations.
   - Asynchronous Telegram alerts for fills, trail ratchets, trade exits, and 15-minute telemetry digests.

---

## Quickstart & Deployment

### 1. Configure Credentials
Copy the example credentials file and input your Binance Futures Testnet API keys and Telegram credentials:
```bash
cp app_credentials.py.example app_credentials.py
nano app_credentials.py
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch NexusSniper
```bash
./start.sh
```

Web Dashboard: http://localhost:8000
Supervisor Logs: ./logs/dashboard.log
