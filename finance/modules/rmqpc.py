import pika


def get_channel(conn_params):
    return pika.BlockingConnection(conn_params).channel()


def declare_exchange_to_channel(channel, exch_name, exch_type):
    channel.exchange_declare(exchange=exch_name, exchange_type=exch_type)


def declare_queue_to_channel(channel, qname, exclusive=None):  # todo, if for simple queue exclusive is not defined
    if exclusive is None:
        channel.queue_declare(queue=qname)
    else:
        channel.queue_declare(queue=qname, exclusive=exclusive)


def bind_exch_to_queue(channel, exch_name, qname):
    channel.queue_bind(exchange=exch_name, queue=qname)


def set_queue_callback(channel, qname, callback, auto_ack=True):
    channel.basic_consume(queue=qname, on_message_callback=callback, auto_ack=auto_ack)


def consumer_simple_channel_setup(conn_params, qname, callback):
    channel = get_channel(conn_params)
    declare_queue_to_channel(channel, qname)
    set_queue_callback(channel, qname, callback)
    return channel


def producer_simple_channel_setup(conn_params, qname):
    channel = get_channel(conn_params)
    declare_queue_to_channel(channel, qname)
    return channel


def consumer_exch_channel_setup(conn_params, qname, callback, exch_name, exch_type):
    channel = get_channel(conn_params)
    declare_exchange_to_channel(channel, exch_name, exch_type)
    declare_queue_to_channel(channel, qname, exclusive=True)
    bind_exch_to_queue(channel, exch_name, qname)
    set_queue_callback(channel, qname, callback)
    return channel


def producer_exch_channel_setup(conn_params, exch_name, exch_type):
    channel = get_channel(conn_params)
    declare_exchange_to_channel(channel, exch_name, exch_type)
    return channel


class Consumer:
    def __init__(self, conn_params, qname, callback, exch_name='', exch_type='fanout'):
        self.__conn_params = conn_params
        self.__qname = qname
        self.__callback = callback
        self.__exch_name = exch_name
        self.__exch_type = exch_type
        self.__channel = self.__setup_channel()

    def __setup_channel(self):
        if self.__exch_name == '':
            return consumer_simple_channel_setup(self.__conn_params, self.__qname, self.__callback)
        else:
            return consumer_exch_channel_setup(self.__conn_params, self.__qname, self.__callback,
                                               self.__exch_name, self.__exch_type)

    def start_consuming(self):
        print("start consuming...")
        self.__channel.start_consuming()


class Producer:
    def __init__(self, conn_params, qname=None, exch_name='', exch_type='fanout'):
        self.__conn_params = conn_params
        self.__qname = qname
        self.__exch_name = exch_name
        self.__exch_type = exch_type
        self.__channel = self.__setup_channel()

    def __setup_channel(self):
        if self.__exch_name == '':
            return producer_simple_channel_setup(self.__conn_params, self.__qname)
        else:
            return producer_exch_channel_setup(self.__conn_params, self.__exch_name, self.__exch_type)

    def send(self, data):  # todo what about routing_key in the setup?
        self.__channel.basic_publish(exchange=self.__exch_name, routing_key='', body=data.tobytes())
