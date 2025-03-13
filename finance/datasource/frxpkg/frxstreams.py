import asyncio
import threading
import time
from typing import Optional, Dict, Callable, Any

from finance.datasource.frxpkg.rcwebsocket import ReconnectingWebsocket
from finance.utilities.uio import ulog

KEEPALIVE_TIMEOUT = 5 * 60  # 5 minutes


# ThreadedWebsocketManager has been put in ThreadedApiManager and ThreadedApiManager has been renamed to ForexTWM
class ForexThreadedWebsocketManager(threading.Thread):  # old: ThreadedApiManager(threading.Thread)

    def __init__(self, frx_listener_log_file, rwc_log_file):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()         # ThreadedApiManager
        self._log = ulog.get_default_logger(__name__, frx_listener_log_file)
        self._running: bool = True                                               # ThreadedApiManager
        self._socket_running: Dict[str, bool] = {}                               # ThreadedApiManager

        self._fsm: Optional[ForexSocketManager] = None                           # ThreadedWebsocketManager in binance
        self._rwc_log_file = rwc_log_file

    #  ---------------------- ThreadedApiManager(threading.Thread) ----------------------
    async def _before_socket_listener_start(self):
        self._fsm = ForexSocketManager(self._rwc_log_file, self._loop)           # ThreadedWebsocketManager in binance

    async def socket_listener(self):
        await self._before_socket_listener_start()
        while self._running:
            await asyncio.sleep(0.2)
        while self._socket_running:
            await asyncio.sleep(0.2)

    async def start_listener(self, socket, path: str, callback):
        async with socket as s:
            while self._socket_running[path]:
                try:
                    # print("frxstream-waiting-main")
                    msg = await asyncio.wait_for(s.recv(), 65)  # todo (1): config
                    # print("frxstream-received-main")
                except asyncio.TimeoutError:
                    self._log.warning("timeout")
                    print("frxstream-timeout")
                    continue
                if not msg:
                    self._log.warning("frxstream-invalid-msg")
                    print("frxstream-invalid-msg")
                    continue
                callback(msg)
        del self._socket_running[path]

    def run(self):
        self._loop.run_until_complete(self.socket_listener())

    def stop_socket(self, socket_name):
        if socket_name in self._socket_running:
            self._socket_running[socket_name] = False

    def stop(self):
        if not self._running:
            return
        self._running = False
        for socket_name in self._socket_running.keys():
            self._socket_running[socket_name] = False

    #  ---------------------- End of ThreadedApiManager(threading.Thread) ----------------------

    #  ---------------------- ThreadedWebsocketManager(ThreadedApiManager)  in binance ----------------------

    def _start_async_socket(
        self, callback: Callable, socket_name: str, params: Dict[str, Any], path: Optional[str] = None
    ) -> str:
        while not self._fsm:
            time.sleep(0.1)
        socket = getattr(self._fsm, socket_name)(**params)
        path = path or socket._path  # noqa
        self._socket_running[path] = True
        self._loop.call_soon(asyncio.create_task, self.start_listener(socket, socket._path, callback))
        return path

    def start_kline_futures_socket(self, callback: Callable, symbol: str, interval) -> str:
        return self._start_async_socket(
            callback=callback,
            socket_name='kline_socket',
            params={
                'symbol': symbol,
                'interval': interval,
            }
        )

    #  ---------------------- End of ThreadedWebsocketManager(ThreadedApiManager)  in binance----------------------


# ------------- ForexSocketManager ----------------

class ForexSocketManager:

    def __init__(self, log_file, loop=None, user_timeout=KEEPALIVE_TIMEOUT):
        self._conns = {}
        self._loop = loop or asyncio.get_event_loop()
        self._user_timeout = user_timeout
        self._log_file = log_file

    def _get_stream_url(self):  # todo: complete this in advanced version (see the original version in Binance package)
        stream_url = 'ws://localhost'  # wss not working
        return stream_url

    def _get_socket(self, path: str, prefix: str = 'ws/', is_binary: bool = False):
        if path not in self._conns:
            self._conns[path] = ReconnectingWebsocket(
                loop=self._loop,
                path=path,
                url=self._get_stream_url(),
                prefix=prefix,
                exit_coro=self._exit_socket,
                is_binary=is_binary,
                log_file=self._log_file,
            )

        return self._conns[path]

    def kline_socket(self, symbol: str, interval):  # getattr(self._fsm, socket_name)(**params) in ForexThreadedWebsocketManager will call this
        path = f'{symbol.lower()}@kline_{interval}'
        return self._get_socket(path, prefix='ws/')  # if you want multiple sybmols, remove this prefix

    async def _exit_socket(self, path: str):
        await self._stop_socket(path)

    async def _stop_socket(self, conn_key):
        if conn_key not in self._conns:
            return

        del(self._conns[conn_key])

