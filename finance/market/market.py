import queue


class Order:
    """
    :type otype: str or None
    :type curr_price: float or None
    """

    def __init__(self, otype, curr_price):
        self.otype = otype
        self.curr_price = curr_price


class Market:
    """
    :type _order: Order or None
    """
    def __init__(self):
        self._order = None

    def get_curr_order(self):
        """
        :return:
        :rtype: Order
        """
        return self._order


class MarketSimulator(Market):
    """
    :type __order_queue: multiprocessing.Queue
    """
    def __init__(self, order_queue):
        super().__init__()
        self.__order_queue = order_queue
        self.__order = None

    def get_curr_order(self):  # todo (1) separate set order
        try:
            order = self.__order_queue.get(block=True, timeout=0.001)  # todo get timeout from config
            self.__order = order
            return self.__order
        except queue.Empty:
            return self.__order


class MarketConfig:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
