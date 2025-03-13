from abc import ABC, abstractmethod

import pika

from finance.modules.rmqpc import Producer


class DataSourceInterface(ABC):

    @abstractmethod
    def ready_to_receive_next_candle(self):
        pass


class DSInterfaceMultiProc(DataSourceInterface):

    def __init__(self, mpqueue):
        self.mpqueue = mpqueue

    def ready_to_receive_next_candle(self):
        self.mpqueue.put(1)


class DSInterfaceRabbitMQ(DataSourceInterface):
    def __init__(self, exch_name):
        self.__producer = None
        self.__received_data = False
        self.__init_producer(exch_name)

    def __init_producer(self, exch_name):
        conn_params = pika.ConnectionParameters()  # todo (check does 'local host' work or not)
        self.__producer = Producer(conn_params, exch_name=exch_name)

    def ready_to_receive_next_candle(self):
        self.__producer.send(1)

