"""
cTrader Open API - Python Client
Webhook-ready, async WebSocket client for trading bots
"""

import asyncio
import websockets
import json
import logging
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Message type constants (from cTrader API docs)
MSG_APPLICATION_AUTH_REQ = 2100
MSG_APPLICATION_AUTH_RES = 2101
MSG_ACCOUNT_AUTH_REQ = 2102
MSG_ACCOUNT_AUTH_RES = 2103
MSG_ACCOUNT_LOGOUT_REQ = 2104
MSG_ACCOUNT_LOGOUT_RES = 2105

class cTraderAPI:
    def __init__(self, client_id: str, client_secret: str, access_token: str, account_id: int):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = account_id
        self.ws_url = "wss://demo.ctraderapi.com:5036"  # Use demo for testing
        self._ws = None
        self._connected = False
        self._msg_handlers = {}
        self._client_msg_id = 0
        
    def _next_msg_id(self) -> str:
        self._client_msg_id += 1
        return f"msg_{self._client_msg_id}"
    
    async def connect(self) -> bool:
        """Establish WebSocket connection and authenticate"""
        try:
            self._ws = await websockets.connect(self.ws_url)
            
            # Step 1: Application auth
            await self._send({
                "clientMsgId": self._next_msg_id(),
                "payloadType": MSG_APPLICATION_AUTH_REQ,
                "payload": {
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret
                }
            })
            
            resp = await self._recv()
            if resp.get("payloadType") != MSG_APPLICATION_AUTH_RES:
                logger.error(f"App auth failed: {resp}")
                return False
            
            # Step 2: Account auth
            await self._send({
                "clientMsgId": self._next_msg_id(),
                "payloadType": MSG_ACCOUNT_AUTH_REQ,
                "payload": {
                    "ctidTraderAccountId": self.account_id,
                    "accessToken": self.access_token
                }
            })
            
            resp = await self._recv()
            if resp.get("payloadType") != MSG_ACCOUNT_AUTH_RES:
                logger.error(f"Account auth failed: {resp}")
                return False
                
            self._connected = True
            logger.info(f"Connected to account {self.account_id}")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    async def _send(self, msg: dict):
        """Send JSON message"""
        if self._ws:
            await self._ws.send(json.dumps(msg))
            
    async def _recv(self) -> Optional[dict]:
        """Receive one JSON message"""
        if self._ws:
            try:
                msg = await asyncio.wait_for(self._ws.recv(), timeout=10)
                return json.loads(msg)
            except asyncio.TimeoutError:
                return None
        return None
    
    async def close(self):
        """Close connection"""
        if self._ws:
            await self._ws.close()
            self._connected = False

    async def listen(self, handler: Callable[[dict], None]):
        """Listen for messages and call handler"""
        if not self._ws:
            return
        try:
            while self._connected:
                msg = await self._ws.recv()
                data = json.loads(msg)
                handler(data)
        except websockets.ConnectionClosed:
            logger.info("Connection closed")
        finally:
            self._connected = False
