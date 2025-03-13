import asyncio
import threading
from time import sleep

from autobahn.asyncio import WebSocketServerProtocol, WebSocketServerFactory


class WebSocketServer(WebSocketServerProtocol):
    connections = list()
    first_msg_has_been_sent = False

    def onConnect(self, request):
        print("Client connected.")
        self.connections.append(self)

    def onClose(self, wasClean, code, reason):
        print("Client disconnected.")
        self.connections.remove(self)
        if self.connections == 0:
            self.first_msg_has_been_sent = False

    def onMessage(self, payload, is_binary):
        pass

    # todo other events

    def init(self):
        pass

    def start(self):
        pass

    @classmethod
    def broadcast(cls, msg):
        # print(f"Num. of connections {len(cls.connections)}")
        for conn in cls.connections:
            payload = msg.encode('utf8')
            # print(f"Broadcasting candle: {payload}")
            conn.sendMessage(payload, )
            # print(f"Candle has been broadcasted.")
            if cls.first_msg_has_been_sent is False:  # don't move this out of the loop to be sure that there is at least one connection
                cls.first_msg_has_been_sent = True

    @classmethod
    def get_conn_num(cls):
        return len(cls.connections)


def establish_web_socket_server(host, port, thread_loop, socket_ready):
    asyncio.set_event_loop(thread_loop)  # should be set before factory = WebSocketServerFactory()
    factory = WebSocketServerFactory()
    factory.protocol = WebSocketServer

    coro = thread_loop.create_server(factory, host, port)  # todo config
    server = None

    try:
        print("Simulated socket server starting ...")
        server = thread_loop.run_until_complete(coro)
        socket_ready.set()
        thread_loop.run_forever()
    except Exception as exp:
        print(exp)
    finally:
        if server:
            server.close()
        thread_loop.close()
        print("Simulated socket server closed.")


def start_sim_server_with_socket(raw_hist, host, port, waiting_queue=None):
    """
    :param list[str] raw_hist:
    :param str host:
    :param int port:
    :param multiprocessing.Queue waiting_queue:
    :return:
    """

    loop = asyncio.new_event_loop()  # asyncio.get_event_loop()
    socket_ready = threading.Event()

    threading.Thread(target=establish_web_socket_server, args=(host, port, loop, socket_ready)).start()
    socket_ready.wait()

    print("######################## SENDING CANDLES (1m) ########################")

    count = 0
    while count < len(raw_hist):
        while WebSocketServer.get_conn_num() == 0:
            for raw_candle in raw_hist[count:]:
                if WebSocketServer.get_conn_num() > 0:
                    break
                WebSocketServer.broadcast(raw_candle)
                print(f"Candle {count} was sent - no client")
                sleep(30)
                count += 1
                if count >= len(raw_hist):
                    break
        while WebSocketServer.get_conn_num() > 0 and count < len(raw_hist):
            for raw_candle in raw_hist[count:]:
                if WebSocketServer.get_conn_num() == 0:
                    break
                if WebSocketServer.first_msg_has_been_sent:  # now could wait on queue (if exists)
                    if waiting_queue is not None:  # waiting_queue is not None in EXE_OFFLINE_SS_FAST mode
                        print("Waiting on queue...")
                        waiting_queue.get()
                WebSocketServer.broadcast(raw_candle)
                print(f"Candle {count} was sent - at least one client")
                count += 1
                if count >= len(raw_hist):
                    break

    print("#################################################################")
    print("All candles 1m have been sent.")


def start_sim_server_without_socket(data_provider, hist_1m, waiting_queue):
    """
    :param finance.dataprovider.data_provider.DataProvider data_provider:
    :param list[finance.models.candles.Candle] hist_1m:
    :param multiprocessing.Queue waiting_queue:
    :return:
    """

    print("######################## SENDING CANDLES ########################")

    # sending first candle is necessary because of waiting_queue
    candle = hist_1m[0]
    data_provider.on_new_candle_1m_sim(candle)

    for candle in hist_1m[1:, :]:
        waiting_queue.get()  # waiting_queue is not None in EXE_OFFLINE_SS_FAST mode

        data_provider.on_new_candle_1m_sim(candle)

    print("#################################################################")
    print("All candles 1m have been sent.")
