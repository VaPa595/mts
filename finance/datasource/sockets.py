from abc import ABC, abstractmethod

"""
More than one socket of any type (candle, tick, ...) could be defined
"""


class CandleSocket(ABC):
    @abstractmethod
    def init(self):
        pass

    @abstractmethod
    def start(self, symbol, candle_interval, callback):  # todo (1) is it possible to define type of call_back in docstring?
        # It is based on the idea of socket/stream in binance.ThreadedWebsocketManager
        """
        :param str symbol:
        :param str candle_interval:
        :param callback:
        """
        pass

    @abstractmethod
    def stop(self):
        pass


# define other socket, i.e. tick socket

