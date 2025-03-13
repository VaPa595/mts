class SLine:
    """
    :var price: price of the exterma
    :type price: float
    :var extype: minimum or maximum
    :type extype: str
    :var interval: time interval, i.e. 1m, 15m, 1h, ...
    :type interval: str
    :var time: time of occurring
    :type time: int
    :var hits: number of hits
    :type hits: int
    """
    def __init__(self, price, extype, interval, time, hits):
        self.price = price
        self.extype = extype
        self.interval = interval
        self.time = time
        self.hits = hits

