import asyncio
from abc import ABC, abstractmethod


class SocketHandler(asyncio.Protocol, ABC):

    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        # peer_name = transport.get_extra_info('peername')
        # print('Connection from {}'.format(peer_name))
        self.transport = transport
        self.on_connect()

    def data_received(self, data):  # todo: IMP type
        self.on_message(data)

    def connection_lost(self, exc):
        self.on_close()

    @abstractmethod
    def on_connect(self):
        pass

    @abstractmethod
    def on_message(self, data):
        # message = data.decode()
        pass

    @abstractmethod
    def on_close(self):
        pass

    @abstractmethod
    def send(self, data):
        # self.transport.write(bytes(msg, 'utf-8'))
        pass


class SocketCollection:
    """
    :type __count: int
    :type __sockets: list[SocketHandler]
    """
    def __init__(self):
        self.__count = 0
        self.__sockets = []

    def add(self, socket):
        self.__sockets.append(socket)
        self.__count += 1

    def remove(self, socket):
        if socket in self.__sockets:
            self.__sockets.remove(socket)
        else:
            print("ERROR: trying to remove socket which doesn't exist ")

    def contains(self, socket):
        return socket in self.__sockets

    def broadcast(self, data):
        for socket in self.__sockets:
            socket.send(data)

# Server example
# class DataProviderSocketHandler(SocketHandler):  # server side of each opening socket
#     """
#     :type __socket_collection: SocketCollection
#     """
#
#     def __init__(self, socket_collection):
#         super().__init__()
#         self.__socket_collection = socket_collection
#
#     def on_connect(self):
#         peer_name = self.transport.get_extra_info('peer-name')
#         print('Connection from {}'.format(peer_name))
#         self.__socket_collection.add(self)
#
#     def on_message(self, data):
#         # message = data.decode()
#         # print('Data received: {!r}'.format(message))
#         pass
#
#     def on_close(self):
#         self.__socket_collection.remove(self)
#
#     def send(self, data):
#         """
#         :param bytearray data:
#         """
#         self.transport.write(data)

# Client example
# class DecisionMakerSocketHandler(SocketHandler):
#     """
#     :type __decision_maker: DecisionMaker
#     """
#
#     def __init__(self, loop, decision_maker):
#         super().__init__()
#         self.loop = loop
#         self.__decision_maker = decision_maker
#
#     def on_connect(self):
#         pass
#
#     def on_message(self, data):
#         if data.decode() == DP_UPDATED:
#             self.__decision_maker.on_data_provider_update()
#
#     def on_close(self):
#         print("DecisionMaker socket is closed.")
#         self.loop.stop()  # todo: IMP:     loop.call_soon_threadsafe(loop.stop)
#
#     def send(self, data):
#         pass


# self.__server_loop.call_soon_threadsafe(self.__server_loop.stop)
#