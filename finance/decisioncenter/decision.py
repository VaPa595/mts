class Decision:
    """
    :type oside: str
    :type otype: str
    :type otime: str
    :type volume: float
    :type price: float or None
    :type sl: float or None
    :type tp: float or None
    """

    # open order and parameters, close order and parameters,
    def __init__(self, oside, otype, otime, volume, price=None, sl=None, tp=None):
        """
        :param str oside: order side: buy or sell.
        :param str otype: order type: market, stop, limit, etc.
        :param str otime: order time
        :param float volume: order volume
        :param float price: order price
        :param float sl: stop lost
        :param float tp: take profit
        """
        self.oside = oside
        self.otype = otype
        self.volume = volume
        self.otime = otime
        self.price = price
        self.sl = sl
        self.tp = tp

    def __str__(self):
        return f"oside:{self.otype}, otype:{self.otype}, otime:{self.otime}, volume:{self.volume}, " \
               f"price:{self.price}, sl:{self.sl}, tp:{self.tp}"

