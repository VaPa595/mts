
class Trade:
    """
    :type side: str
    :type type: str
    :type open_time: int
    :type open_price: float
    :type close_time: int or None
    :type close_price: float or None
    :type initial_volume: float
    :type curr_volume: float
    :type benefit: float
    :type benefit_prcg: float
    """
    def __init__(self, trade_side, trade_type, open_time, open_price, volume=1):
        self.side = trade_side  # Buy or Sell
        self.type = trade_type  # market, stop_limit, ...
        self.open_time = open_time
        self.open_price = open_price
        self.close_time = None
        self.close_price = None
        self.initial_volume = volume
        self.curr_volume = volume
        self.benefit = 0
        self.benefit_prcg = 0


# Redundant:
# class TradeState:
#     def __init__(self, state, trade):
#         self.state = state  # new, open, close, None
#         self.trade = trade


class TradeStateTracker:
    """
    :type __config: TradeStateTrackerConfig
    :type __market: Market
    :type __trade_state_queue: multiprocessing.Queue
    :type trade_state: str or None
    :type trade: Trade or None
    """
    def __init__(self, config, market, trade_state_queue):
        self.__config = config
        self.__market = market
        self.__trade_state_queue = trade_state_queue
        self.trade_state = None  # new, open, close, None
        self.trade = None

    def update_trade_state(self):  # todo (1)
        pass

    def start(self):  # todo (1)
        pass


class TradeStateTrackerConfig:
    """
    :type bale_bot_config: finance.binance.config.BaleBotConfig
    :type mpqueue_config: finance.binance.config.MPQueueConfig
    :type log_file: str
    """

    def __init__(self, bale_bot_config, mpqueue_config, log_file):
        self.bale_bot_config = bale_bot_config
        self.mpqueue_config = mpqueue_config
        self.log_file = log_file




