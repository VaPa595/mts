import asyncio
import gzip
import json
import logging
from enum import Enum
from random import random
from socket import gaierror
from typing import Optional

import websockets as ws
from websockets.exceptions import ConnectionClosedError

from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.uio import ulog


class WSListenerState(Enum):
    INITIALISING = 'Initialising'
    STREAMING = 'Streaming'
    RECONNECTING = 'Reconnecting'
    EXITING = 'Exiting'


class ReconnectingWebsocket:
    MAX_RECONNECTS = 100
    MAX_RECONNECT_SECONDS = 120
    MIN_RECONNECT_WAIT = 0.1
    TIMEOUT = 90
    NO_MESSAGE_RECONNECT_TIMEOUT = 120
    MAX_QUEUE_SIZE = 100

    def __init__(
            self, log_file, url: str, path: Optional[str] = None, prefix: str = 'ws/', is_binary: bool = False,
            exit_coro=None
    ):  # loop has been removed as argument in binance 1.0.17
        self._loop = asyncio.get_event_loop()
        self._log = ulog.get_default_logger(__name__, log_file)
        self._path = path
        self._url = url
        self._exit_coro = exit_coro
        self._prefix = prefix
        self._reconnects = 0
        self._is_binary = is_binary
        self._conn = None
        self._socket = None
        self.ws: Optional[ws.WebSocketClientProtocol] = None  # type: ignore
        self.ws_state = WSListenerState.INITIALISING
        # self.reconnect_handle = None # removed in binance 1.0.17
        self._queue = asyncio.Queue()  # new in binance 1.0.17
        self._handle_read_loop = None  # new in binance 1.0.17

        self.max_reconn_count = 0
        self.max_queue_count = 0

        self._bale_bot = BaleBot(token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')  # todo (1) get from config

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._exit_coro:
            await self._exit_coro(self._path)
        self.ws_state = WSListenerState.EXITING
        if self.ws:
            self.ws.fail_connection()
        if self._conn and hasattr(self._conn,
                                  'protocol'):  # "and hasattr(self._conn, 'protocol')" is new in binance 1.0.17
            await self._conn.__aexit__(exc_type, exc_val, exc_tb)
        self.ws = None
        if not self._handle_read_loop:  # new in binance 1.0.17
            print("rcw_CANCEL read_loop")
            self._log.error("CANCEL read_loop")  # new in binance 1.0.17
            await self._kill_read_loop()  # new in binance 1.0.17

    async def connect(self):
        await self._before_connect()
        assert self._path
        # ws_url = self._url + self._prefix + self._path
        ws_url = create_ws_url(self._url, self._prefix, self._path)
        self._conn = ws.connect(ws_url, close_timeout=0.1)  # type: ignore  # "close_timeout" is new in binance 1.0.17
        try:
            self.ws = await self._conn.__aenter__()
        except:  # noqa
            await self._reconnect()
            return
        self.ws_state = WSListenerState.STREAMING
        self._reconnects = 0
        await self._after_connect()

        # To manage the "cannot call recv while another coroutine is already waiting for the next message"
        if not self._handle_read_loop:  # new in binance 1.0.17
            self._handle_read_loop = self._loop.call_soon_threadsafe(asyncio.create_task,
                                                                     self._read_loop())  # new in binance 1.0.17

    async def _kill_read_loop(self):  # new in binance 1.0.17
        self.ws_state = WSListenerState.EXITING
        while self._handle_read_loop:
            await asyncio.sleep(0.1)

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
            print(f'rcw_error parsing evt json:{evt}')
            self._log.debug(f'error parsing evt json:{evt}')
            return None

    async def _read_loop(self):  # new in binance 1.0.17 similar to recv() in old version
        try:
            while True:
                try:
                    while self.ws_state == WSListenerState.RECONNECTING:
                        await self._run_reconnect()

                    if self.ws_state == WSListenerState.EXITING:
                        print(f"rcw_read_loop {self._path} break for {self.ws_state}")
                        self._log.debug(f"_read_loop {self._path} break for {self.ws_state}")
                        break
                    elif self.ws.state == ws.protocol.State.CLOSING:  # type: ignore
                        await asyncio.sleep(0.1)
                        continue
                    elif self.ws.state == ws.protocol.State.CLOSED:  # type: ignore
                        await self._reconnect()
                    elif self.ws_state == WSListenerState.STREAMING:
                        assert self.ws
                        res = await asyncio.wait_for(self.ws.recv(), timeout=self.TIMEOUT)
                        res = self._handle_message(res)
                        if res:
                            self._log.info(f"final_msg: {res}")
                            if self._queue.qsize() > 1:
                                self._log.warning(f"Queue Size {self._queue.qsize()}.")
                            if self._queue.qsize() < self.MAX_QUEUE_SIZE:
                                await self._queue.put(res)
                                self.max_queue_count = 0
                            else:
                                print(f"rcw_Queue overflow {self.MAX_QUEUE_SIZE}. Message not filled")
                                self._log.debug(f"Queue overflow {self.MAX_QUEUE_SIZE}. Message not filled")
                                # await self._queue.put({
                                #     'e': 'error',
                                #     'm': 'Queue overflow. Message not filled'
                                # })
                                self.max_queue_count = self.max_queue_count + 1
                                if self.max_queue_count > 100:
                                    await self._bale_bot.send_message(chat_id='4426980252',
                                                                      text="rcw_queue overflow_program has been exited")  # todo (1) get from config
                                    exit(-2)
                                raise Exception("RCW_Queue overflow")  # raise BinanceWebsocketUnableToConnect
                except asyncio.TimeoutError:
                    print(f"rcw_read_loop_no message in {self.TIMEOUT} seconds")
                    self._log.debug(f"_read_loop_no message in {self.TIMEOUT} seconds")
                    # _no_message_received_reconnect
                except asyncio.CancelledError as e:
                    print(f"rcw_cancelled error {e}")
                    self._log.debug(f"cancelled error {e}")
                    break
                except asyncio.IncompleteReadError as e:
                    print(f"rcw_incomplete read error ({e})")
                    self._log.debug(f"incomplete read error ({e})")
                except ConnectionClosedError as e:
                    print(f"rcw_connection close error ({e})")
                    self._log.debug(f"connection close error ({e})")  # different from old version (here only log)
                except gaierror as e:
                    print(f"rcw_DNS Error ({e})")
                    self._log.debug(f"DNS Error ({e})")
                # except BinanceWebsocketUnableToConnect as e:  # todo (0) import this from new binance  # new in binance 1.0.167
                #     self._log.debug(f"BinanceWebsocketUnableToConnect ({e})")
                #     break
                except Exception as e:
                    print(f"rcw_Unknown exception: ({e})")
                    self._log.debug(f"Unknown exception: ({e})")
                    await self._bale_bot.send_message(chat_id='4426980252',
                                                      text="rcw_Unknown exception")  # todo (1) get from config
                    if "exit" in str(e):
                        await self._bale_bot.send_message(chat_id='4426980252',
                                                          text="rcw_program has been exited")  # todo (1) get from config
                        exit(-3)
                    continue
        finally:
            self._handle_read_loop = None  # Signal the coro is stopped
            self._reconnects = 0

    async def _run_reconnect(self):  # new in binance 1.0.17
        await self.before_reconnect()
        if self._reconnects < self.MAX_RECONNECTS:
            reconnect_wait = self._get_reconnect_wait(self._reconnects)
            print(f"rcw_websocket reconnecting. {self.MAX_RECONNECTS - self._reconnects} reconnects left - "
                  f"waiting {reconnect_wait}"
                  )
            self._log.debug(
                f"websocket reconnecting. {self.MAX_RECONNECTS - self._reconnects} reconnects left - "
                f"waiting {reconnect_wait}"
            )
            await asyncio.sleep(reconnect_wait)
            await self.connect()
        else:
            # my changes
            # # Signal the error
            # await self._queue.put({
            #     'e': 'error',
            #     'm': 'Max reconnect retries reached'
            # })

            # self.max_reconn_count = self.max_reconn_count + 1  # todo (1) remove self.max_reconn_count
            # if self.max_reconn_count < 100:
            #     print(f'rcw_Max reconnections {self.MAX_RECONNECTS} reached:')
            #     self._log.error(f'Max reconnections {self.MAX_RECONNECTS} reached')
            #     # exit(-3)
            print(f'rcw_Max reconnections {self.MAX_RECONNECTS} reached:')
            self._log.error(f'Max reconnections {self.MAX_RECONNECTS} reached')
            await self._bale_bot.send_message(chat_id='4426980252',
                                              text=f"Max reconnections {self.MAX_RECONNECTS} reached")  # todo (1) get from config
            raise Exception("RCW_Max reconnections - exit program")  # raise BinanceWebsocketUnableToConnect

    async def recv(self):  # very different than old version (most in new _read_loop)
        res = None
        while not res:
            try:
                res = await asyncio.wait_for(self._queue.get(), timeout=self.TIMEOUT)
            except asyncio.TimeoutError:
                print(f"rcw_recv_no message in {self.TIMEOUT} seconds")
                self._log.debug(f"recv_no message in {self.TIMEOUT} seconds")
        return res

    async def _wait_for_reconnect(self):
        while self.ws_state != WSListenerState.STREAMING and self.ws_state != WSListenerState.EXITING:  # different than old version: while self.ws_state == WSListenerState.RECONNECTING:
            await asyncio.sleep(0.1)

    def _get_reconnect_wait(self, attempts: int) -> int:
        expo = 2 ** attempts
        return round(random() * min(self.MAX_RECONNECT_SECONDS, expo - 1) + 1)

    async def before_reconnect(self):
        if self.ws and self._conn:  # "and self._conn" is new in binance 1.0.17
            await self._conn.__aexit__(None, None, None)
            self.ws = None
        self._reconnects += 1

    def _no_message_received_reconnect(self):
        #  asyncio.create_task(self._reconnect())             # in old version
        print('rcw_No message received, reconnecting')
        self._log.debug('No message received, reconnecting')  # new in binance 1.0.17
        self.ws_state = WSListenerState.RECONNECTING  # new in binance 1.0.17

    async def _reconnect(self):  # very different than old veriosn
        self.ws_state = WSListenerState.RECONNECTING  # new in binance 1.0.17

    # async def _try_handle_msg(self, res):  # has been removed in binance 1.0.17


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
    raise Exception(f"RCW_Invalid path for socket connection: {path}")
