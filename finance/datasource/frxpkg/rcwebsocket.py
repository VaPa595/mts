import asyncio
import gzip
import json
from enum import Enum
from random import random
from typing import Optional

import websockets as ws

from finance.utilities.uio import ulog


class WSListenerState(Enum):
    INITIALISING = 'Initialising'
    STREAMING = 'Streaming'
    RECONNECTING = 'Reconnecting'
    EXITING = 'Exiting'


class ReconnectingWebsocket:
    MAX_RECONNECTS = 1
    MAX_RECONNECT_SECONDS = 120
    MIN_RECONNECT_WAIT = 0.1
    TIMEOUT = 90
    NO_MESSAGE_RECONNECT_TIMEOUT = 120

    def __init__(
            self, loop, log_file, url: str, path: Optional[str] = None, prefix: str = 'ws/', is_binary: bool = False,
            exit_coro=None):
        self._loop = loop or asyncio.get_event_loop()
        self._log = ulog.get_default_logger(__name__, log_file)
        self._path = path
        self._url = url
        self._exit_coro = exit_coro
        self._prefix = prefix
        self._reconnects = 0
        self._is_binary = is_binary
        self._conn = None
        self._socket = None
        self.ws = None
        self.ws_state = WSListenerState.INITIALISING
        self.reconnect_handle = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._exit_coro:
            await self._exit_coro(self._path)
        self.ws_state = WSListenerState.EXITING
        if self.ws:
            self.ws.fail_connection()
        if self._conn:
            await self._conn.__aexit__(exc_type, exc_val, exc_tb)
        self.ws = None

    async def connect(self):
        await self._before_connect()
        assert self._path
        ws_url = create_ws_url(self._url, self._prefix, self._path)
        self._conn = ws.connect(ws_url)
        try:
            self.ws = await self._conn.__aenter__()
        except:  # noqa
            await self._reconnect()
            return
        self.ws_state = WSListenerState.STREAMING
        self._reconnects = 0
        await self._after_connect()

    async def _before_connect(self):
        pass

    async def _after_connect(self):
        pass

    def _handle_message(self, evt):
        if self._is_binary:
            try:
                evt = gzip.decompress(evt)
            except (ValueError, OSError):
                return None
        try:
            return json.loads(evt)
        except ValueError:
            print(f'RCW_error parsing evt json:{evt}')
            self._log.debug(f'RCW_error parsing evt json:{evt}')
            return None

    async def recv(self):
        res = None
        while not res:
            try:
                # print(f"RCW_wait_for: self.ws.recv()")
                res = await asyncio.wait_for(self.ws.recv(), timeout=self.TIMEOUT)  # res is of type 'str'
            except asyncio.TimeoutError:
                print(f"RCW_no message in {self.TIMEOUT} seconds")
                self._log.warning(f"No message in {self.TIMEOUT} seconds")
            except asyncio.CancelledError as e:
                print(f"cancelled error {e}")
                self._log.warning(f"cancelled error {e}")
            except asyncio.IncompleteReadError as e:
                print(f"RCW_incomplete read error {e}")
                self._log.warning(f"incomplete read error {e}")
            except ws.ConnectionClosed as e:
                # print(f"RCW_connection closed {e}")  # this print might be many
                self._log.warning(f"connection closed {e}")
                if self.ws_state != WSListenerState.EXITING:
                    await self._wait_for_reconnect()
            except Exception as e:
                print(f"RCW_exception {e}")
                self._log.warning(f"exception {e}")

                if not self.ws:
                    print("RCW_invalid websocket object")
                    self._log.warning("Invalid websocket object")
                else:
                    print(f"RCW_websocket state {self.ws_state}")
                    self._log.warning(f"websocket state {self.ws_state}")
                raise Exception("RWC_Unwanted Exception")
            else:
                if self.ws_state == WSListenerState.EXITING:
                    self._log.warning(f"break_while_loop_1")
                    print(f"RCW_break_while_loop_1")
                    break
                # print(f"RCW_received_mag: {res}")  # {"OpenTime":1676115780.000000, "Open":21688.2, ... }
                # print(type(res))
                # print(f"RCW_wait_for_try_handle_msg(res)")
                res = await self._try_handle_msg(
                    res)  # res is of type 'dict' now. (_try_handle_msg returns json.loads(res))
                if self.ws_state == WSListenerState.EXITING:
                    self._log.warning(f"break_while_loop_2")
                    print(f"RCW_break_while_loop_2")
                    break
        # print(f"RCW_result_after_msg_handling: {res}")  # res is now of type dict : {'OpenTime': 1676115780.0, 'Open': 21688.2, ...}
        # print(type(res))
        self._log.info(f"final_msg: {res}")
        return res

    async def _wait_for_reconnect(self):
        count = 0
        while self.ws_state == WSListenerState.RECONNECTING:
            count = count + 1
            if count >= 100:
                raise Exception("Cannot reconnect!!!!")
            # print("RCW_reconnecting waiting for connect")  # this print might be many
            self._log.warning("RCW_reconnecting waiting for connect")
            await asyncio.sleep(0.1)
        if not self.ws:
            print("RCW_ wait for reconnect--no ws--")
            self._log.warning("RCW_ignore message --no ws--")
        else:
            print(f"RCW_wait for reconnect-websocket state {self.ws_state}")
            self._log.warning(f"wait for reconnect-websocket state {self.ws_state}")

    async def _try_handle_msg(self, res):
        msg_res = self._handle_message(res)
        if msg_res:
            # cancel error timeout (why it is an error)
            if self.reconnect_handle:
                # print(f"RCW_reconnect_handle.cancel - Received msg: {msg_res}")  # NO PROBLEM IS HERE
                self.reconnect_handle.cancel()
            self.reconnect_handle = self._loop.call_later(
                self.NO_MESSAGE_RECONNECT_TIMEOUT, self._no_message_received_reconnect
            )
        return msg_res

    def _get_reconnect_wait(self, attempts: int) -> int:
        expo = 2 ** attempts
        return round(random() * min(self.MAX_RECONNECT_SECONDS, expo - 1) + 1)

    async def before_reconnect(self):
        if self.ws:
            await self._conn.__aexit__(None, None, None)
            self.ws = None
        self._reconnects += 1

    def _no_message_received_reconnect(self):
        print('RCW_No message received, reconnecting')
        self._log.warning('RCW_No message received, reconnecting')
        asyncio.create_task(self._reconnect())

    async def _reconnect(self):
        if self.ws_state == WSListenerState.RECONNECTING:
            return
        self.ws_state = WSListenerState.RECONNECTING
        if self.reconnect_handle:
            print("RCW_reconnect_handle.cancel")
            self._log.warning('RCW_reconnect_handle.cancel')
            self.reconnect_handle.cancel()
        await self.before_reconnect()
        if self._reconnects < self.MAX_RECONNECTS:
            reconnect_wait = self._get_reconnect_wait(self._reconnects)
            print(
                f"RCW_websocket reconnecting {self.MAX_RECONNECTS - self._reconnects} reconnects left - "
                f"waiting {reconnect_wait}")
            self._log.warning(
                f"RCW_websocket reconnecting {self.MAX_RECONNECTS - self._reconnects} reconnects left - "
                f"waiting {reconnect_wait}"
            )
            await asyncio.sleep(reconnect_wait)
            await self.connect()
        else:
            print(f"RCW_Max reconnection {self.MAX_RECONNECTS} reached")
            self._log.error(f"Max reconnection {self.MAX_RECONNECTS} reached")
            raise Exception("RCW_Unable to connect")  # it returns pass


def create_ws_url(url, prefix, path):
    # return url + prefix + path  # default from binance lib
    # not in forex ths symbol is BTCUSD not BTCUSDT
    if path == "btcusd@kline_1m":  # {symbol.lower()}@kline_{interval}
        return url + ":54286"
    if path == "btcusd@kline_15m":
        return url + ":54287"
    if path == "btcusd@kline_1h":
        return url + ":54288"
    if path == "btcusd@kline_4h":
        return url + ":54289"
    raise Exception("RCW_Invalid path for socket connection")
