import asyncio
import ccxt.pro as ccxtpro
import ccxt.async_support as ccxt
import pandas as pd
import config
import state_store

class NetworkMesh:
    def __init__(self):
        self.ws_exchange = None
        self.rest_exchange = None
        self.live_tickers = {}
        self.is_connected = False

    async def initialize(self):
        state_store.log("Initializing CCXT Network Mesh...")
        
        self.ws_exchange = ccxtpro.binanceusdm({
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })

        self.rest_exchange = ccxt.binanceusdm({
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'future', 'adjustForTimeDifference': True}
        })

        if config.USE_TESTNET:
            # FIXED: CCXT syntax for Binance Demo testnet (bypasses sandbox crash)
            self.ws_exchange.enable_demo_trading(True)
            self.rest_exchange.enable_demo_trading(True)

        await self.rest_exchange.load_markets()
        self.is_connected = True
        state_store.log("Network Mesh connected to Binance.")

    async def start_ticker_stream(self, symbols):
        while True:
            try:
                tickers = await self.ws_exchange.watch_tickers(symbols)
                for sym, t in tickers.items():
                    if t.get('last') is not None:
                        self.live_tickers[sym] = float(t['last'])
            except Exception as e:
                state_store.log(f"WS Ticker Stream hiccup: {e}. Reconnecting...", "WARN")
                await asyncio.sleep(2)

    async def fetch_ohlcv_hybrid(self, symbol, timeframe, limit=100):
        try:
            ohlcv = await asyncio.wait_for(
                self.ws_exchange.watch_ohlcv(symbol, timeframe, limit=limit),
                timeout=3.0
            )
        except Exception:
            try:
                ohlcv = await self.rest_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as rest_err:
                state_store.log(f"OHLCV fetch failed for {symbol}: {rest_err}", "ERROR")
                return pd.DataFrame()

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    def get_live_price(self, symbol):
        return self.live_tickers.get(symbol)

    async def close(self):
        if self.ws_exchange: await self.ws_exchange.close()
        if self.rest_exchange: await self.rest_exchange.close()
