import asyncio
from asyncio import sleep

from binance.enums import KLINE_INTERVAL_1MINUTE  # todo(1) define enums independent of binance package

from finance.datasource.frxpkg.frx_converter import ForexDataConverter
# from finance.datasource.frxpkg.frxstreams import ForexThreadedWebsocketManager  # old
from finance.datasource.frxpkg.frxstreamsnew import ForexThreadedWebsocketManager
from finance.datasource.sockets import CandleSocket
from finance.utilities.ufinance import common


def callback_decorator(callback):
    def final_callback(msg):
        new_candle_1m = ForexDataConverter.socket_candle_to_candle_object(msg, KLINE_INTERVAL_1MINUTE)
        callback(new_candle_1m)

    return final_callback


class ForexCandleSocket(CandleSocket):
    def __init__(self, frx_listener_log_file, rwc_log_file):  # todo (1): docstring
        self.twm = ForexThreadedWebsocketManager(frx_listener_log_file, rwc_log_file)

    def init(self):
        self.twm.start()

    def start(self, callback, symbol, candle_interval):
        final_callback = callback_decorator(callback)
        self.twm.start_kline_futures_socket(callback=final_callback, symbol=symbol, interval=candle_interval)

    def stop(self):
        self.twm.stop()  # all stream will be stopped


def print_msg(msg):
    print(msg)


async def main():
    soc = ForexCandleSocket("FRX_Listener_Test.log", "RWC_Test.log")

    # func = getattr(soc, 'salam')
    # print(func())
    #
    # msg = getattr(soc, 'salam')()
    # print(msg)

    soc.init()
    soc.start(print_msg, 'BTCUSDT', '1m')
    await sleep(360)
    soc.stop()


if __name__ == '__main__':
    asyncio.run(main())
