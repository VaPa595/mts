import queue

import pandas as pd

from finance.market.market import Market, Order
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.uio import ulog
from finance.utilities.utime import TicToc


class TradeState:  # todo (2) think to create new instance of TradeState on each order (in multiple orders case)
    """
    :type __config: TradeConfig
    """

    def __init__(self, trade_config):
        self.__config = trade_config
        self.__order_type = None
        self.curr_profit = None  # todo (1) IMP: where and when to update?
        self.curr_profit_percentage = None
        self.touching_min_profit_before_deadline = False
        self.touching_hard_stop_limit = False
        self.reaching_min_profit_deadline = False
        self.touching_min_profit = False
        self.touching_profit_ceiling = False
        self.touching_adaptive_stop_limit = False  # todo (3): it is not configured
        self.update_time = None

    def reset(self):
        self.__order_type = None
        self.curr_profit = None
        self.curr_profit_percentage = None
        self.touching_min_profit_before_deadline = False
        self.touching_hard_stop_limit = False
        self.reaching_min_profit_deadline = False
        self.touching_min_profit = False
        self.touching_profit_ceiling = False
        self.touching_adaptive_stop_limit = False
        self.update_time = None

    def update_trade_config(self, trade_config):
        """
        :param TradeConfig trade_config:
        """
        self.__config = trade_config

    def set_order_type(self, order_type):
        """
        :param str or None order_type:
        """
        self.__order_type = order_type

    def get_order_type(self):
        """
        :return:
        :rtype: str
        """
        return self.__order_type

    def exist_an_open_trade(self):
        return self.__order_type is not None

    def get_profit_ceiling(self):
        return self.__config.profit_ceiling

    def get_max_loss_after_touching_profit_ceiling(self):
        return self.__config.max_loss_after_touching_profit_ceiling

    def __str__(self):
        if self.__order_type is None:
            return "No Open Trade"
        return f"OrderType: {self.__order_type}, CurrProfit: {self.curr_profit} CurrProfitPercentage: " \
               f"{self.curr_profit_percentage}, " \
               f"TouchingMinProfitBeforeDeadline: {self.touching_min_profit_before_deadline}, " \
               f"TouchingHardStopLimit: {self.touching_hard_stop_limit}, " \
               f"ReachingMinProfitDeadline: {self.reaching_min_profit_deadline}" \
               f"TouchingMinProfit: {self.touching_min_profit}" \
               f"TouchingProfitCeiling: {self.touching_profit_ceiling}" \
               f"TouchingAdaptiveStopLimit: {self.touching_adaptive_stop_limit}"


class TradeStateTrackerConfig:
    """
    :type trade_config: TradeConfig
    :type bale_bot_config: finance.binance.config.BaleBotConfig
    :type mpqueue_config: finance.binance.config.MPQueueConfig
    :type log_file: str
    """

    def __init__(self, trade_config, bale_bot_config, mpqueue_config, log_file):
        self.trade_config = trade_config
        self.bale_bot_config = bale_bot_config
        self.mpqueue_config = mpqueue_config
        self.log_file = log_file


class TradeStateTracker:
    """
    :type __config: TradeStateTrackerConfig
    :type __market: Market
    :type __hist_1m_df_queue: multiprocessing.Queue
    :type __trade_state_queue: multiprocessing.Queue
    :type __hist_1m_df: pd.DataFrame or None
    :type __trade_state: TradeState
    :type __order: Order or None
    :type __exe_mode: str
    """

    def __init__(self, config, market, hist_1m_queue, trade_state_queue,
                 exe_mode):
        self.__config = config
        self.__market = market
        self.__order = None
        self.__hist_1m_df_queue = hist_1m_queue
        self.__trade_state_queue = trade_state_queue
        self.__price_at_opening_order = None
        self.__timer = None
        self.__trade_state = TradeState(self.__config.trade_config)  # todo (5): IMP, how to init?
        self.__exe_mode = exe_mode

        self.__tic_toc = TicToc()

        self.__bale_bot = BaleBot(token=self.__config.bale_bot_config.token,
                                  base_url=self.__config.bale_bot_config.base_url)
        self.__chat_id = self.__config.bale_bot_config.trade_chat_id

        # # Shouldn't be called in init when using hist_1m_df
        # # Just for clean code: (no need to use ump.get_from_queue)
        # self.__hist_1m_df = ump.get_from_queue(self.__hist_1m_df_queue, timeout=0.001)
        self.__hist_1m_df = None

        self.__logger = ulog.get_default_logger(__name__, self.__config.log_file)

    def start(self):
        # while not shutdown_event.is_set():
        # no need to use ump.get_from_queue
        while True:
            try:
                data = self.__hist_1m_df_queue.get(block=True, timeout=self.__config.mpqueue_config.timeout)
                # print(f"Trader: get hist - {self.__hist_1m_df_queue.qsize()}")
                # self.__update_hist_1m(data)  # if list of candles is added
                self.__hist_1m_df = data
                self.__on_new_data()
            except queue.Empty:
                continue

    def __on_new_data(self):
        curr_order = self.__get_curr_order_from_market()

        self.__handle_change_on_order_state(curr_order)

        self.__update_trade_state()

        # todo (3): doc: that only one object (original) object is send not its copy
        self.__trade_state_queue.put(self.__trade_state)  # todo (6) may be need to modified what should be pickled
        # print(f"Trader: put trade - {self.__trade_state_queue.qsize()}")

        # only send if an order is open:
        # self.__bale_bot.send(self.__trade_state.__str__(), chat_id=self.__chat_id)

    def __update_trade_state(self):
        self.__trade_state.update_time = self.__get_curr_time()
        if self.exist_an_open_trade():
            self.__update_curr_profit()
            self.__update_curr_profit_percentage()
            self.__update_touching_hard_stop_limit_status()
            self.__update_touching_min_profit_status_before_deadline()  # should be before updating timer
            self.__update_deadline_timer_and_perform_corresponding_actions()
            self.__update_reaching_min_profit_deadline_status()
            self.__update_touching_profit_ceiling_status()

    def __update_curr_profit(self):
        curr_price = self.__get_curr_close_price()
        if self.__order.otype == "BUY":
            self.__trade_state.curr_profit = curr_price - self.__price_at_opening_order
        else:  # otype == "SELL"
            self.__trade_state.curr_profit = self.__price_at_opening_order - curr_price

    def __update_curr_profit_percentage(self):
        self.__trade_state.curr_profit_percentage = self.__trade_state.curr_profit / self.__price_at_opening_order

    def __update_touching_hard_stop_limit_status(self):
        self.__trade_state.touching_hard_stop_limit = self.__trade_state.curr_profit_percentage < \
                                                      self.__config.trade_config.hard_stop_limit

    def __update_touching_min_profit_status_before_deadline(self):
        # todo (6): doc, it may some times be true and other times be false
        if self.__timer > 0:
            self.__trade_state.touching_min_profit = \
                self.__trade_state.curr_profit >= self.__config.trade_config.min_profit

    def __update_deadline_timer_and_perform_corresponding_actions(self):
        if self.__timer > 0:
            self.__timer -= 1  # todo (1): if missing data? --> user datetime -- handle and test with simulation
            if self.__timer == 0 and self.__trade_state.touching_min_profit:
                self.__trade_state.touching_min_profit_before_deadline = True

    def __update_reaching_min_profit_deadline_status(self):
        self.__trade_state.reaching_min_profit_deadline = self.__timer == 0  # todo (1): IMP, if timer never is set

    def __update_touching_profit_ceiling_status(self):
        if self.__trade_state.curr_profit >= self.__config.trade_config.profit_ceiling:
            self.__trade_state.touching_profit_ceiling = True  # at least one touch

    def __get_curr_order_from_market(self):
        """
        :return:
        :rtype: Order
        """
        return self.__market.get_curr_order()

    def __handle_change_on_order_state(self, order_at_market):  # todo (1): emergent: check the method again
        """
        :param Order order_at_market:
        """
        if self.exist_an_open_trade():  # todo: rename: in this class not in the Market class
            if order_at_market is None:
                self.__on_close_order()
                self.__logger.info("Order is closed in market directly.")
            elif self.__last_order_is_closed_and_new_is_open(order_at_market):
                self.__on_close_order()  # last order is closed
                self.__on_open_order(order_at_market)  # new order is opened
                self.__logger.info("Last order is closed and new one is opened (both directly).")
            elif self.__secondary_changes_at_market(order_at_market):
                self.__on_secondary_changes_at_market(order_at_market)  # todo IMP: may not be necessary
        elif order_at_market is not None:
            self.__on_open_order(order_at_market)
            self.__logger.info("Order is opened in market directly.")
        if self.__last_order_has_just_been_closed(order_at_market):
            self.__on_close_order()
            self.__logger.info("Last order is closed.")

    def __last_order_has_just_been_closed(self, order_at_market):
        return self.__order is not None and order_at_market is None

    def __secondary_changes_at_market(self, order_at_market):
        # an order
        return False  # todo (2), IMP

    def __last_order_is_closed_and_new_is_open(self, order_at_market):
        return False  # todo (2), emergent,

    def __on_open_order(self, order):
        """
        :param finance.binance.market.Order order:
        """
        self.__order = order
        self.__trade_state.set_order_type(order.otype)
        # todo (1): what if the order is opened directly using other tools
        self.__price_at_opening_order = order.curr_price
        self.__config.trade_config.adaptive_stop_limit = \
            self.__config.trade_config.adaptive_stop_limit_rate * self.__price_at_opening_order
        self.__timer = self.__config.trade_config.min_profit_deadline

    def __on_secondary_changes_at_market(self, order):  # not primary changes which means it is new order
        # update trade_state
        pass

    def __on_close_order(self):  # todo (3): IMP, for temporary, calculate profit or loss hear.
        if self.__order is not None:  # todo (2), could be a situation with no order while calling close order?-->test
            self.__order = None
            self.__trade_state.reset()

    def exist_an_open_trade(self):
        return self.__order is not None

    def get_trade_state(self):
        return self.__trade_state

    def __get_curr_close_price(self):
        # NOTE: DON'T USE hist_1m, IT SHOULD BE pd.DataFrame (__hist_1m_df)
        # close_prices = common.get_df_hist_field_data(self.__hist_1m_df, 'close')
        # return close_prices.iloc[-1]
        return self.__hist_1m_df.iloc[-1].close

    def __get_curr_open_price(self):
        return self.__hist_1m_df.iloc[-1].open

    def __get_curr_time(self):
        """
        :return: returns close_time of the last candle in the history
        :rtype: int
        """
        return self.__hist_1m_df.iloc[-1].close_time

    def update_trade_config(self, trade_config):
        """
        Note: Some changes will no affect trade state until next hist_1m. Also, update trade_config has no effect on
        __timer.
        :param TradeConfig trade_config:
        """
        self.__config.trade_config = trade_config
        self.__trade_state.update_trade_config(trade_config)

    # todo (1) always check trade state from dataprovider(the market): see following
    # - fetch current order
    # - do we need to check it is updated? --> only some thresholds may be change, or it is closed and new order
    # is opened --> how should we know it is a new order? check some critical parameters like open price, or volume, ...
    # ..., if it is new order, then some updates should be done by TradeStateTracker
    # -  if at the start of the project, an order is already exists, some necessary parameters should be set manually
    # ... (in case of they couldn't be fetched from Market), then the other processes could be continued.
    # - how we can be notified here than the order is closed? and on which state of the market? remember the maximum...
    # ... delay is 1 minute. So, if there is no order, it means it is close at most 1 minute ago. and we have all...
    # ...previous histories.
    # So, it means we have every thing we want for now.


class TradeConfig:
    """
    :type hard_stop_limit: float
    :type profit_ceiling: float
    :type max_loss_after_touching_profit_ceiling: float
    :type min_profit_deadline: int
    :type min_profit: float  # todo (2) profit_floor
    :type adaptive_stop_limit_rate: float
    :type adaptive_stop_limit: float or None
    """

    def __init__(self, hard_stop_limit, profit_ceiling, max_loss_after_touching_profit_ceiling, min_profit_deadline,
                 min_profit, adaptive_stop_limit_rate):
        self.hard_stop_limit = hard_stop_limit
        self.profit_ceiling = profit_ceiling
        self.max_loss_after_touching_profit_ceiling = max_loss_after_touching_profit_ceiling
        self.min_profit_deadline = min_profit_deadline
        self.min_profit = min_profit
        self.adaptive_stop_limit_rate = adaptive_stop_limit_rate
        self.adaptive_stop_limit = None
