# todo it is not the app, it is just one of the main engines of the application

import asyncio
import json
import logging
import threading

from autobahn.asyncio import WebSocketServerProtocol, WebSocketServerFactory

from finance.utilities.ufinance import common
from finance.dataprovider.data_consumer import HistConsumer
from finance.dataprovider.data_provider import DataProvider
from finance.market.trade_state_brk import TradeState
from finance.models.messages import HeaderPayloadMessage

# todo: better structure
from finance.utilities.uio import ulog


class TraderWebSocket(WebSocketServerProtocol):
    __logger = ulog.get_default_logger(__name__, 'TraderWebSocket.log', logging.DEBUG)
    connections = list()

    def onConnect(self, request):
        print("Client connected.")
        self.connections.append(self)
        self.__logger.info("New client connected")

    def onClose(self, wasClean, code, reason):
        self.connections.remove(self)
        self.__logger.info("Client disconnected")

    def onMessage(self, payload, is_binary):
        msg = payload.decode('utf8')
        self.__logger.info("Matlab call: " + msg)
        print("Matlab call:" + msg)
        if msg == 'reset':  # todo config
            # self.finance_app.reset()
            for conn in self.connections:
                if conn is not self:
                    conn.sendClose()

    # todo other events

    @classmethod
    def send_msg(cls, msg):
        for conn in cls.connections:
            payload = msg.encode('utf8')
            conn.sendMessage(payload, )
        # print("New msg to clients")
        # cls.__logger.info("New msg to clients")


def start_websocket(host, port):
    def threaded_websocket(event_loop, ready):
        asyncio.set_event_loop(event_loop)  # should be set before factory = WebSocketServerFactory()
        factory = WebSocketServerFactory()
        factory.protocol = TraderWebSocket  # don't us instance of the class

        coro = event_loop.create_server(factory, host, port)  # todo config
        server = None

        try:
            server = event_loop.run_until_complete(coro)
            ready.set()
            event_loop.run_forever()
        except Exception as exp:
            print(exp)
        finally:
            if server:
                server.close()
            event_loop.close()

    loop = asyncio.new_event_loop()  # asyncio.get_event_loop()
    thread_is_ready = threading.Event()

    threading.Thread(target=threaded_websocket, args=(loop, thread_is_ready)).start()
    thread_is_ready.wait()
    print("WebSocket is started ...")


class SocketBasedDataConsumer(HistConsumer):

    def on_new_hist(self, candle_interval, history):
        """
        :param str candle_interval:
        :param deque[Candle] history:
        """
        hist_str = common.create_hist_str(history)
        msg = HeaderPayloadMessage(header=candle_interval, payload=hist_str)
        socket_msg = json.dumps(msg.__dict__)
        self.__send_socket_msg(socket_msg)

    def on_new_tick(self, candle_interval):  # due to concurrency problem, let matlab detects ticks it-self
        # msg_header = "Tick" + candle_interval
        # hlines_json = None  #
        # msg = HeaderPayloadMessage(header=msg_header, payload=hlines_json)
        # socket_msg = json.dumps(msg.__dict__)
        # self.__send_socket_msg(socket_msg)
        pass

    @staticmethod
    def __send_socket_msg(socket_msg):
        TraderWebSocket.send_msg(socket_msg)


class Trader:

    # todo: no need to symbol, api_key, api_secret?
    def __init__(self, symbol, api_key, api_secret):
        """
        :param symbol:
        :param api_key:
        :param api_secret:
        :param DataProvider data_provider:
        :param DecisionMaker decision_maker:
        :param TradeState trade_state:
        """
        self.__logger = ulog.get_default_logger(__name__, 'BinanceTrader.log', logging.DEBUG)
        # self.__data_provider = data_provider
        # self.__decision_maker = decision_maker
        # dm_data_consumer = DMDataConsumer(decision_maker)  # todo think of better approach
        # self.__data_provider.add_full_consumer(dm_data_consumer)
        # self.__trade_state = trade_state

    def start(self):
        start_websocket('127.0.0.1', 9001)
        # todo another socket for receiving
        # self.__data_provider.start()

    def stop(self):
        # todo stop websocket
        pass

    def start_test(self, test_name, curr_time):  # todo: trader should not know anything about test
        start_websocket('127.0.0.1', 9001)
        # self.__data_provider.start_test(test_name, curr_time)

    def stop_test(self):
        pass









