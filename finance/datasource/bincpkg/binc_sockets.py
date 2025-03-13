import asyncio
from asyncio import sleep

from binance import ThreadedWebsocketManager
from binance.enums import KLINE_INTERVAL_1MINUTE

from finance.datasource.sockets import CandleSocket
from finance.utilities.ufinance import common


def verify_candle_socket_msg(msg, candle_interval):
    """
    :param dict msg: raw candle received by websocket
    :param str candle_interval:
    """
    if msg['e'] == 'error':
        raise Exception("Socket " + candle_interval + " Error (probably is disconnected)")


def is_a_complete_socket_candle(socket_candle_msg):
    return socket_candle_msg['k']['x']


def convert_socket_candle_to_simple_model(socket_msg, candle_interval):
    """
    :param dict socket_msg:
    :param str candle_interval:
    :return:
    :rtype: Candle
    """
    candle_model = common.get_candle_model(candle_interval)

    return candle_model(open=socket_msg['k']['o'], high=socket_msg['k']['h'], low=socket_msg['k']['l'],
                        close=socket_msg['k']['c'], volume=socket_msg['k']['v'], open_time=socket_msg['k']['t'],
                        close_time=socket_msg['k']['T'])


def callback_decorator(callback):
    def final_callback(msg):
        verify_candle_socket_msg(msg, KLINE_INTERVAL_1MINUTE)
        if is_a_complete_socket_candle(msg):

            new_candle_1m = convert_socket_candle_to_simple_model(msg, KLINE_INTERVAL_1MINUTE)
            callback(new_candle_1m)

    return final_callback


class BinanceCandleSocket(CandleSocket):
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret)

    def init(self):
        self.twm.start()

    def start(self, callback, symbol, candle_interval):
        # self.twm.start_kline_socket(callback=self.handle_socket_message, symbol=self.symbol,
        #                             interval=KLINE_INTERVAL_1MINUTE, )

        self.twm.start_kline_futures_socket(callback=callback, symbol=symbol, interval=candle_interval)

    def stop(self):
        self.twm.stop()  # all stream will be stopped

    def salam(self):
        print("helloooooooo")
        return "salammmmmm"


def print_msg(msg):
    print(msg)


async def main():
    api_key = "plZs99V1J2je95KHRBiVa6HG8fUZlS169X2Wc0woqbeGSF0drOP7Y5uljZQrgXao"
    api_secret = "wBi65iknjQeWDo63albZP44YvoJUiLTtx1H4fn8eTct5U0g40cSNFBVyTCbcMJNF"

    soc = BinanceCandleSocket(api_key, api_secret)

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

