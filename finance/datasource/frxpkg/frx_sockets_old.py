import socket

from finance.datasource.sockets import CandleSocket


class ForexCandleSocket(CandleSocket):
    def __init__(self, host, port):  # todo (1): docstring
        self.__host = host
        self.__port = port
        self.__socket = None

    def init(self):
        try:
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print("Socket (for forex) successfully created")
        except socket.error as err:
            print(f"socket (for forex) creation failed with error {err}")

    def start(self, callback, symbol, candle_interval):
        try:
            self.__socket.connect(self.__host, self.__port)
            print("Socket (for forex) is successfully connected.")
        except socket.error as err:
            print(f"socket (for forex) connection failed with error {err}")

    def stop(self):
        try:
            self.__socket.close()
            print("Socket (for forex) is successfully closed.")
        except socket.error as err:
            print(f"socket (for forex) closing failed with error {err}")

