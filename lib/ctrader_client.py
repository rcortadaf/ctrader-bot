"""
cTrader OpenAPI Python Client
Async WebSocket client per trading i backtesting
"""

import asyncio
import websockets
import json
import time
import logging
from typing import Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Message type constants
MSG_APPLICATION_AUTH_REQ = 2100
MSG_APPLICATION_AUTH_RES = 2140
MSG_ACCOUNT_AUTH_REQ = 2102
MSG_ACCOUNT_AUTH_RES = 2141
MSG_GET_TRENDBARS_REQ = 2137
MSG_GET_TRENDBARS_RES = 2138
MSG_ERROR = 2142
MSG_GET_ACCOUNT_INFO_REQ = 9032
MSG_GET_ACCOUNT_INFO_RES = 9033
MSG_SUBSCRIBE_REQ = 109
MSG_SUBSCRIBE_RES = 110
MSG_GET_OBSERVABLE_REQ = 113
MSG_GET_OBSERVABLE_RES = 114
MSG_PLACE_ORDER_REQ = 13
MSG_PLACE_ORDER_RES = 14
MSG_CLOSE_ORDER_REQ = 15
MSG_CLOSE_ORDER_RES = 16

# Period constants (cTrader)
PERIOD_M1 = 1
PERIOD_H1 = 2
PERIOD_H4 = 3
PERIOD_D1 = 4
PERIOD_W1 = 5
PERIOD_MN1 = 6

PERIOD_NAMES = {
    PERIOD_M1: "M1",
    PERIOD_H1: "H1", 
    PERIOD_H4: "H4",
    PERIOD_D1: "D1",
    PERIOD_W1: "W1",
    PERIOD_MN1: "MN"
}

class cTraderClient:
    def __init__(self, client_id: str, client_secret: str, access_token: str, account_id: int, ws_url: str = "wss://demo.ctraderapi.com:5036"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = account_id
        self.ws_url = ws_url
        self._ws = None
        self._connected = False
        self._client_msg_id = 0
        self._msg_id_to_type = {}
        
    def _next_msg_id(self) -> str:
        self._client_msg_id += 1
        return f"c_{self._client_msg_id}"
    
    async def connect(self) -> bool:
        """Connect and authenticate"""
        try:
            self._ws = await websockets.connect(self.ws_url, max_size=2*1024*1024)
            
            # App auth
            msg_id = self._next_msg_id()
            await self._send({
                "clientMsgId": msg_id,
                "payloadType": MSG_APPLICATION_AUTH_REQ,
                "payload": {
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret
                }
            })
            resp = await self._recv()
            if not resp or resp.get("payloadType") != MSG_APPLICATION_AUTH_RES:
                logger.error(f"App auth failed: {resp}")
                return False
            
            # Account auth
            msg_id = self._next_msg_id()
            await self._send({
                "clientMsgId": msg_id,
                "payloadType": MSG_ACCOUNT_AUTH_REQ,
                "payload": {
                    "ctidTraderAccountId": self.account_id,
                    "accessToken": self.access_token
                }
            })
            resp = await self._recv()
            if not resp or resp.get("payloadType") != MSG_ACCOUNT_AUTH_RES:
                logger.error(f"Account auth failed: {resp}")
                return False
            
            self._connected = True
            logger.info(f"Connected to account {self.account_id}")
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    async def _send(self, msg: dict):
        if self._ws:
            await self._ws.send(json.dumps(msg))
            
    async def _recv(self) -> Optional[dict]:
        if self._ws:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=30)
                return json.loads(msg)
            except asyncio.TimeoutError:
                return None
        return None
    
    async def _call(self, payload_type: int, payload: dict, timeout: float = 30) -> Optional[dict]:
        """Send request and wait for response"""
        if not self._ws:
            return None
        
        msg_id = self._next_msg_id()
        msg = {
            "clientMsgId": msg_id,
            "payloadType": payload_type,
            "payload": payload
        }
        
        await self._send(msg)
        
        # Wait for matching response
        start = time.time()
        while time.time() - start < timeout:
            resp = await self._recv()
            if resp and resp.get("clientMsgId") == msg_id:
                return resp
        return None
    
    async def get_trendbars(self, symbol_id: int, period: int, from_ts: int, to_ts: int) -> List[dict]:
        """Get historical trendbars (candlesticks)"""
        payload = {
            "ctidTraderAccountId": self.account_id,
            "symbolId": symbol_id,
            "period": period,
            "fromTimestamp": from_ts,
            "toTimestamp": to_ts
        }
        
        resp = await self._call(MSG_GET_TRENDBARS_REQ, payload)
        if resp and resp.get("payloadType") == MSG_GET_TRENDBARS_RES:
            return resp.get("payload", {}).get("trendbar", [])
        return []
    
    async def close(self):
        if self._ws:
            await self._ws.close()
            self._connected = False
    
    async def get_historical_data(self, symbol_id: int, period: int, days: int = 180) -> List[dict]:
        """
        Get historical data in chunks to avoid message size limits.
        Returns list of bars with: timestamp, open, high, low, close, volume
        """
        now_ms = int(time.time() * 1000)
        chunk_ms = 30 * 24 * 3600 * 1000  # 30-day chunks
        
        all_bars = []
        from_ts = now_ms - days * 24 * 3600 * 1000
        
        current_from = from_ts
        while current_from < now_ms:
            current_to = min(current_from + chunk_ms, now_ms)
            
            bars = await self.get_trendbars(symbol_id, period, current_from, current_to)
            all_bars.extend(bars)
            
            if bars:
                logger.info(f"Got {len(bars)} bars from {current_from} to {current_to}")
            else:
                logger.warning(f"No bars returned for {current_from} to {current_to}")
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.3)
            current_from = current_to
        
        return all_bars
    
    def parse_trendbars(self, bars: List[dict]) -> List[dict]:
        """
        Parse cTrader trendbar format to standard OHLC.
        cTrader uses delta values from the 'low' field as the base price.
        """
        parsed = []
        for bar in bars:
            low = bar.get('low', 0) / 1000.0  # low is in thousandths (e.g., 118004 = 1180.04)
            delta_open = bar.get('deltaOpen', 0) / 1000.0
            delta_close = bar.get('deltaClose', 0) / 1000.0
            delta_high = bar.get('deltaHigh', 0) / 1000.0
            
            # Convert timestamp (minutes) to datetime
            ts_min = bar.get('utcTimestampInMinutes', 0)
            dt = datetime.utcfromtimestamp(ts_min * 60)
            
            parsed.append({
                'timestamp': dt,
                'time': ts_min * 60,
                'open': low + delta_open,
                'high': low + delta_high,
                'low': low,
                'close': low + delta_close,
                'volume': bar.get('volume', 0)
            })
        
        return parsed

    async def get_account_info(self) -> dict:
        """Get account balance and info."""
        resp = await self._call(MSG_GET_ACCOUNT_INFO_REQ, {
            "ctidTraderAccountId": self.account_id
        })
        if resp and resp.get("payloadType") == MSG_GET_ACCOUNT_INFO_RES:
            return resp.get("payload", {})
        return {}

    async def subscribe(self, symbol_ids: List[int]) -> bool:
        """Subscribe to one or more symbols for live data."""
        resp = await self._call(MSG_SUBSCRIBE_REQ, {
            "ctidTraderAccountId": self.account_id,
            "symbolIds": symbol_ids
        })
        return resp and resp.get("payloadType") == MSG_SUBSCRIBE_RES

    async def place_order(self, symbol_id: int, side: str, volume: float,
                        stop_loss: float = 0, take_profit: float = 0,
                        order_type: str = "market") -> dict:
        """Place an order (buy/sell with SL/TP)."""
        payload = {
            "ctidTraderAccountId": self.account_id,
            "symbolId": symbol_id,
            "tradeSide": "buy" if side == "buy" else "sell",
            "volume": volume,
            "orderType": 1 if order_type == "market" else 2,
        }
        if stop_loss:
            payload["stopLoss"] = int(stop_loss * 100000)
        if take_profit:
            payload["takeProfit"] = int(take_profit * 100000)

        resp = await self._call(MSG_PLACE_ORDER_REQ, payload)
        if resp and resp.get("payloadType") == MSG_PLACE_ORDER_RES:
            return resp.get("payload", {})
        return {}

    async def close_all_positions(self) -> bool:
        """Close all open positions."""
        payload = {
            "ctidTraderAccountId": self.account_id,
            "method": 1  # Close all
        }
        resp = await self._call(MSG_CLOSE_ORDER_REQ, payload)
        return resp and resp.get("payloadType") == MSG_CLOSE_ORDER_RES

    def get_closes(self, count: int = 100) -> list:
        """Get last N close prices from cached bars."""
        if hasattr(self, '_bars_cache'):
            return [b['close'] for b in self._bars_cache[-count:]]
        return []

    def cache_bar(self, bar: dict):
        """Cache a bar for indicator calculation."""
        if not hasattr(self, '_bars_cache'):
            self._bars_cache = []
        self._bars_cache.append(bar)
        if len(self._bars_cache) > 500:
            self._bars_cache.pop(0)
