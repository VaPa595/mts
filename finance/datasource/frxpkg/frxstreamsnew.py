import asyncio
import threading
import time
from typing import Dict, Optional, Callable, Any

from finance.datasource.frxpkg.rcwebsocketnew import ReconnectingWebsocket
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.uio import ulog
from finance.utilities.usys import syscomm


class ThreadedApiManager(threading.Thread):
    # based on new binance version, it should not be merged with ForexThreadedWebsocketManager (because of loop and queue in rcw)

    MAX_TIMEOUT = 10 * 60
    SLEEP_TIME_TO_RESET_ROBO_FOREX = 5 * 60

    def __init__(self, logger):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self._running: bool = True
        self._socket_running: Dict[str, bool] = {}

        self._log = logger

        self._bale_bot = BaleBot(
            token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')  # todo (1) get from config  # same token and chat id in main_dc.py

    async def _before_socket_listener_start(self):
        ...

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
                    msg = await asyncio.wait_for(s.recv(), self.MAX_TIMEOUT)
                except asyncio.TimeoutError:
                    self._log.warning("max_timeout_resetting_robo_forex")
                    print("frxstream-max_timeout_resetting_robo_forex")
                    await self._bale_bot.send_message(chat_id='4426980252',
                                                      text="frxstream_restarting robo_frx")  # todo (1) get from config
                    syscomm.reset_robo_forex()
                    await asyncio.sleep(self.SLEEP_TIME_TO_RESET_ROBO_FOREX)  # take respite till resetting robo forex
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


class ForexThreadedWebsocketManager(ThreadedApiManager):
    def __init__(self, frx_listener_log_file, rwc_log_file):
        logger = ulog.get_default_logger(__name__, frx_listener_log_file)
        super().__init__(logger)
        self._fsm: Optional[ForexSocketManager] = None  # ThreadedWebsocketManager in binance
        self._rwc_log_file = rwc_log_file

    async def _before_socket_listener_start(self):
        # loop argument has been removed from binance 1.0.17  --> old:  ForexSocketManager(self._rwc_log_file, self._loop)
        self._fsm = ForexSocketManager(self._rwc_log_file)  # ThreadedWebsocketManager in binance

    def _start_async_socket(
            self, callback: Callable, socket_name: str, params: Dict[str, Any], path: Optional[str] = None
    ) -> str:
        while not self._fsm:
            time.sleep(0.1)
        socket = getattr(self._fsm, socket_name)(**params)
        socket_path: str = path or socket._path  # noqa
        self._socket_running[socket_path] = True
        self._loop.call_soon_threadsafe(asyncio.create_task, self.start_listener(socket, socket_path, callback))
        return socket_path

    # from old frxstreams.py: (in new binance(1.0.17) pkg start_kline_futures_socket has been defined)
    def start_kline_futures_socket(self, callback: Callable, symbol: str, interval) -> str:
        return self._start_async_socket(
            callback=callback,
            socket_name='kline_socket',
            params={
                'symbol': symbol,
                'interval': interval,
            }
        )


class ForexSocketManager:
    def __init__(self, log_file):  # loop argument has been removed from binance 1.0.17

        self._conns = {}
        self._loop = asyncio.get_event_loop()  # in binance 1.0.17 loop is created here (not probably given from argument)

        self._log_file = log_file

    def _get_stream_url(self):  # todo: complete this in advanced version (see the original version in Binance package)
        stream_url = 'ws://localhost'  # wss not working
        return stream_url

    def _get_socket(self, path: str, prefix: str = 'ws/', is_binary: bool = False):  # mostly from old binance
        if path not in self._conns:
            self._conns[path] = ReconnectingWebsocket(
                # loop=self._loop,  # it has been removed from binance 1.0.17
                path=path,
                url=self._get_stream_url(),
                prefix=prefix,
                exit_coro=self._exit_socket,
                is_binary=is_binary,
                log_file=self._log_file,
            )

        return self._conns[path]

    def kline_socket(self, symbol: str,
                     interval):  # getattr(self._fsm, socket_name)(**params) in ForexThreadedWebsocketManager will call this
        path = f'{symbol.lower()}@kline_{interval}'
        return self._get_socket(path)

    async def _exit_socket(self, path: str):
        await self._stop_socket(path)

    async def _stop_socket(self, conn_key):
        if conn_key not in self._conns:
            return

        del (self._conns[conn_key])
