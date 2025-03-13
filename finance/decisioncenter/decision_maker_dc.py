import jsonpickle
import pandas as pd
from binance.enums import KLINE_INTERVAL_1MINUTE

from finance.decisioncenter.decision import Decision
from finance.market.trade import Trade
from finance.modules.enums import SET_POINT_SELL, SET_POINT_BUY, SIDE_SELL, SIDE_BUY, Frx_ORDER_TYPE_SELL, \
    Frx_ORDER_TYPE_BUY
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.ufinance import common
from finance.market.trade_state_brk import TradeState
from finance.utilities import ump, utime
from finance.utilities.uio import ulog

from finance.analysis.trendstate.trend_state_dc import TrendStateDC
from finance.models.extremum import Extremum


def to_datetime(epoch):
    if epoch is None:
        return None
    return utime.epoch_to_utc_datetime(epoch=epoch, datetime_format="%d-%m-%Y@%H:%M:%S")


class DecisionMaker:
    # todo (1): complete docstring
    """
    :type __config: DecisionConfigDC
    :type __bale_bot: BaleBot or None
    :type __hist_1m_df_queue: multiprocessing.Queue
    :type __trend_state_queue: multiprocessing.Queue
    :type __trade_state_queue: multiprocessing.Queue
    :type __trend_state: TrendStateDC or None
    :type __trade_state: TradeState or None
    :type __decision_queue: multiprocessing.Queue
    :type __hist_1m_df: pd.DataFrame or None
    :typo __curr_trade: Trade or None
    """

    def __init__(self, config, hist_1m_df_queue,
                 trend_state_queue, trade_state_queue, decision_queue, exe_mode):  # todo (1) exe_mode is not used
        self.__config = config

        self.__bale_bot = BaleBot(
            token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')  # todo (1) get from config

        self.__chat_id = self.__config.bale_bot_config.decision_chat_id

        self.__logger = ulog.get_default_logger(__name__, config.log_file)

        self.__hist_1m_df_queue = hist_1m_df_queue
        self.__trend_state_queue = trend_state_queue
        self.__trade_state_queue = trade_state_queue

        self.__trade_state = None
        self.__trend_state = None
        self.__decision_queue = decision_queue
        self.__exe_mode = exe_mode

        self.__hist_1m_df = None

        # algorithm specific
        self.__buy_trade = config.buy_trade
        self.__sell_trade = config.sell_trade

        self.__small_interval = config.small_interval
        self.__large_interval = config.large_interval
        self.__small_atr = None  # 15m or 1h
        self.__large_atr = None  # 4h

        # self.growing_small_candle = None  # 15m or 1h
        # self.growing_large_candle = None  # 4h
        #
        # self.last_large_candle = None  # last completed large candle
        # self.last_small_candle = None  # last completed small candle

        self.__last_small_min = 0
        self.__last_small_max = 0

        self.__set_point = None
        self.__set_points = []
        self.__set_point_has_been_met = False
        self.__set_point_type = None
        self.__stop_loss_point = None
        self.__stop_loss_point_st = None
        self.__half_close_point = None
        self.__full_close_point = None

        self.__extremum_before_sp = None

        self.__curr_trade = None
        self.__trades = []
        self.__total_benefit = 0
        self.__total_benefit_prcg = 0

    def start(self):
        # while not shutdown_event.is_set():
        while True:
            # It was hist_1m_queue before, # See issue #412
            data = ump.get_from_queue(self.__hist_1m_df_queue, timeout=self.__config.mpqueue_config.timeout)
            # print(f"DM: get hist - {self.__hist_1m_df_queue.qsize()}")
            self.__trend_state = ump.get_from_queue(self.__trend_state_queue,
                                                    timeout=self.__config.mpqueue_config.timeout)
            # print(f"DM: get trend - {self.__trend_state_queue.qsize()}")

            # todo (0) for online full version:
            #  currently we have not the complete trade cycle (just alarms)
            # self.__trade_state = ump.get_from_queue(self.__trade_state_queue,
            #                                         timeout=self.__config.mpqueue_config.timeout)

            self.__verify_and_handle_trade_state()
            # print(f"DM: get trade - {self.__trade_state_queue.qsize()}")

            self.__hist_1m_df = data

            # tmp:
            # h1_size = self.__hist_1m_df_queue.qsize()
            # trend_size = self.__trend_state_queue.qsize()
            # trade_size = self.__trade_state_queue.qsize()
            # if h1_size != trend_size or trade_size != trade_size or h1_size != trade_size:
            #     print(f"HSize:{h1_size} -- TrendSize={trend_size} -- TradeSize={trade_size}")
            # tmp end

            self.__on_data_provider_update()
            # except Exception as ex:
            #     print(ex)

    def __verify_and_handle_trade_state(self):
        if self.__trade_is_opened():  # If open order request has changed to position
            self.on_trade_open(None, None, None, None)  # todo (0) for online full version
        elif self.__trade_is_closed():  # If close position request has been accepted
            self.__on_trade_close()

    def __trade_is_opened(self):
        return False  # todo (0) for online full version

    def __trade_is_closed(self):
        return False  # todo (0) for online full version

    def __on_trade_close(self):
        pass  # todo (0) for online full version

    def __on_data_provider_update(self):
        # print("DM: on_data_provider_update")
        candle_1m = self.__get_candle_1m()
        curr_time = self.__get_curr_time()
        # self.__update_required_candles(curr_time, candle_1m)
        self.__update_atrs(curr_time)  # atrs have been updated in TrendState, hear means updating local variables
        if self.__exist_an_open_trade():  # decide to close  # todo (1)
            market_analysis = self.__analyze_closing_conditions()
            decision = self.__make_decision_to_close_order(candle_1m, market_analysis)
            self.__on_close_decision(decision)
            self.__send_decision_and_market_analysis("Close", decision, market_analysis)
        else:  # decide to open
            market_analysis = self.__analyze_opening_conditions()
            decision = self.__make_decision_to_open_order(market_analysis)
            self.__send_decision_and_market_analysis("Open", decision, market_analysis)

    # def __update_required_candles(self, curr_time, candle_1m):
    #     """
    #     :param int curr_time:
    #     :param Candle candle_1m:
    #     :return:
    #     :rtype:
    #     """
    #
    #     if self.growing_large_candle is None:  # it is just after last 4h (beginning of the new 4h)
    #         self.growing_large_candle = candle_1m
    #     else:
    #         self.update_growing_large_candle(candle_1m)
    #         if common.is_tick(curr_time, self.__large_interval):
    #             self.last_large_candle = self.growing_large_candle
    #             self.growing_large_candle = None
    #
    #     if self.growing_small_candle is None:
    #         self.growing_small_candle = candle_1m
    #     else:
    #         self.update_growing_small_candle(candle_1m)
    #         if common.is_tick(curr_time, self.__small_interval):
    #             self.last_small_candle = self.growing_small_candle
    #             self.growing_small_candle = None
    #
    # def update_growing_large_candle(self, new_candle_1m):
    #     """
    #     :param Candle new_candle_1m:
    #     :return:
    #     :rtype: Candle
    #     """
    #     if self.growing_large_candle.high < new_candle_1m.high:
    #         self.growing_large_candle.high = new_candle_1m.high
    #     if self.growing_large_candle.low > new_candle_1m.low:
    #         self.growing_large_candle.low = new_candle_1m.low
    #     self.growing_large_candle.close = new_candle_1m.close
    #     self.growing_large_candle.volume = self.growing_large_candle.volume + new_candle_1m.volume
    #     self.growing_large_candle.close_time = new_candle_1m.close_time
    #
    # def update_growing_small_candle(self, new_candle_1m):
    #     """
    #     :param Candle new_candle_1m:
    #     :return:
    #     :rtype: Candle
    #     """
    #     if self.growing_small_candle.high < new_candle_1m.high:
    #         self.growing_small_candle.high = new_candle_1m.high
    #     if self.growing_small_candle.low > new_candle_1m.low:
    #         self.growing_small_candle.low = new_candle_1m.low
    #     self.growing_small_candle.close = new_candle_1m.close
    #     self.growing_small_candle.volume = self.growing_small_candle.volume + new_candle_1m.volume
    #     self.growing_small_candle.close_time = new_candle_1m.close_time

    def __update_atrs(self, curr_time):
        if common.is_tick(curr_time, self.__small_interval):
            self.__small_atr = self.__trend_state.get_atr(self.__small_interval)
        if common.is_tick(curr_time, self.__large_interval):
            self.__large_atr = self.__trend_state.get_atr(self.__large_interval)

    # def __update_ext_trackers(self, candle_1m):  # should be called after updating atrs
    #     if common.is_tick(candle_1m.close_time + 1, self.__large_interval):
    #         self.large_ext_tracker.on_new_candle(self.last_large_candle)
    #     if common.is_tick(candle_1m.close_time + 1, self.__small_interval):
    #         self.small_ext_tracker.on_new_candle(self.last_small_candle)

    def __exist_an_open_trade(self):
        # return self.__trade_state.exist_an_open_trade()  # todo (0) for online full version
        return False

    def __analyze_opening_conditions(self):
        """
        Some algorithms don't need this method
        :return:
        :rtype: MarketAnalysis or None
        """
        candle_1m = self.__get_candle_1m()
        curr_time = self.__get_curr_time()
        if self.valid_set_point_exist(candle_1m):
            if self.__meet_set_point(candle_1m):
                self.__set_point_has_been_met = True
                self.__logger.info("Set_point is met.")
            if self.__set_point_has_been_met and common.is_tick(curr_time, self.__small_interval):
                self.__logger.info(f"Set_point has been met and new tick {self.__small_interval} is reached.")
                last_small_min = self.__trend_state.get_last_small_min()
                last_small_max = self.__trend_state.get_last_small_max()
                self.update_stop_loss(last_small_max)
                self.update_stop_loss(last_small_min)
                self.update_last_small_min(last_small_min)
                self.update_last_small_max(last_small_max)
                return MarketAnalysis(open_ready=True)
        elif common.is_tick(curr_time, self.__large_interval):  # todo (1) SRP
            log_msg = f"New Tick {curr_time}"
            self.__logger.info(log_msg)

            self.__find_and_store_set_point(candle_1m)
        return MarketAnalysis()  # open_ready is False by default

    def __make_decision_to_open_order(self, market_analysis=None):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: Decision or None
        """
        if market_analysis is None:
            return None
        if market_analysis.open_ready:
            curr_time = self.__get_curr_time()
            last_small_candle = self.__trend_state.get_last_small_candle()
            if common.is_tick(curr_time, self.__small_interval):
                if (self.__set_point_type == SET_POINT_SELL and last_small_candle.close < self.__last_small_min) or \
                        (
                                self.__set_point_type == SET_POINT_BUY and last_small_candle.close > self.__last_small_max):
                    self.__set_point = None
                    return self.create_open_order_decision()
        return None

    def __find_and_store_set_point(self, candle_1m):  # base on new large extremum
        if self.__trend_state.is_new_large_extremum_useful():  # Note: no set_point, no open trade
            new_extremum = self.__trend_state.get_last_large_extremum()  # note: it should be a new extremum

            log_msg = f"New {new_extremum.extype}={new_extremum.price} at {to_datetime(new_extremum.time)}"
            self.__logger.info(log_msg)
            print(log_msg)

            last_large_candle = self.__trend_state.get_last_large_candle()
            if new_extremum.extype == "maximum":
                if self.__sell_trade:
                    self.__set_point = (
                                               new_extremum.price + last_large_candle.low) / 2  # new_extremum.price - 0.8 * self.big_atr  # self.last_candle_4h.low + 1 * self.big_atr #config
                    self.__set_point_type = SET_POINT_SELL

                    log_msg = f"New set_point({self.__set_point_type}): {self.__set_point} at {to_datetime(epoch=candle_1m.close_time)}"
                    self.__logger.info(log_msg)
                    print(log_msg)

                    self.trade_atr = self.__large_atr
                    self.__set_point_has_been_met = False
                    self.__stop_loss_point = 0
                    self.__last_small_min = 0
                    self.__extremum_before_sp = new_extremum
                    self.__set_points.append(
                        SetPoint(new_extremum, self.__set_point_type, self.__set_point, candle_1m.open_time))
            else:
                if self.__buy_trade:
                    self.__set_point = (
                                               new_extremum.price + last_large_candle.high) / 2  # new_extremum.price + 0.8 * self.big_atr  # self.last_candle_4h.high - 1 * self.big_atr #config
                    self.__set_point_type = SET_POINT_BUY

                    log_msg = f"New set_point({self.__set_point_type}): {self.__set_point} at {to_datetime(epoch=candle_1m.close_time)}"
                    self.__logger.info(log_msg)
                    print(log_msg)
                    self.__bale_bot.send_message(chat_id='6183990665', text=log_msg)  # todo (1) get from config

                    self.trade_atr = self.__large_atr
                    self.__set_point_has_been_met = False
                    self.__stop_loss_point = 1000000
                    self.__last_small_min = 0
                    self.__extremum_before_sp = new_extremum
                    self.__set_points.append(
                        SetPoint(new_extremum, self.__set_point_type, self.__set_point, candle_1m.open_time))

    def __send_decision_and_market_analysis(self, mode, decision=None, market_analysis=None):
        msg = self.__decision_to_msg(mode, decision, market_analysis)
        if decision is not None:
            self.__logger.info(msg)
        # self.__bale_bot.send(msg=msg, chat_id=self.__chat_id)
        self.__decision_queue.put(decision)

    def valid_set_point_exist(self, candle_1m):
        """
        :param Candle candle_1m:
        :return:
        :rtype: bool
        """
        if self.__set_point is None:
            return False
        if self.__set_point_type == SET_POINT_SELL and (self.__set_point - candle_1m.low >= 3 * self.trade_atr or
                                                        candle_1m.high > (
                                                                self.__extremum_before_sp.price + 0.3 * self.__large_atr)):  # add stop hunt # default=2atr   #config
            # todo: IMP: what if self.set_point - candle_1m.low <= -2 * self.atr (note, there is no open trade)
            log_msg = f"set_point({self.__set_point_type}): {self.__set_point}  is removed at {to_datetime(epoch=candle_1m.close_time)}"
            self.__logger.info(log_msg)
            print(log_msg)

            self.__set_point = None
            return False
        if self.__set_point_type == SET_POINT_BUY and (self.__set_point - candle_1m.high <= -3 * self.trade_atr or
                                                       candle_1m.low < (
                                                               self.__extremum_before_sp.price - 0.3 * self.__large_atr)):  # default=2atr    #config

            log_msg = f"set_point({self.__set_point_type}): {self.__set_point}  is removed at {to_datetime(epoch=candle_1m.close_time)}"
            self.__logger.info(log_msg)
            print(log_msg)
            self.__bale_bot.send_message(chat_id='6183990665', text=log_msg)  # todo (1) get from config

            self.__set_point = None
            return False
        return True

    def __meet_set_point(self, candle_1m):
        """
        :param Candle candle_1m:
        :return:
        :rtype: bool
        """
        if self.__set_point_type == SET_POINT_SELL:
            if candle_1m.high >= self.__set_point:
                # print(f"set_point({self.set_point_type}): {self.set_point}  is met at "
                # f"{to_datetime(epoch=candle_1m.close_time)}")
                return True
        else:
            if candle_1m.low <= self.__set_point:
                # print(f"set_point({self.set_point_type}): {self.set_point}  is met at "
                # f"{to_datetime(epoch=candle_1m.close_time)}")
                return True
        return False

    def update_stop_loss(self, new_extremum):
        if self.__set_point_type == SET_POINT_SELL:
            if new_extremum.price > self.__stop_loss_point:
                self.__stop_loss_point = new_extremum.price + 0.25 * self.__small_atr  # min(new_extremum.price, (self.small_candle.close + 1.5 * self.big_atr))    # new_extremum.price  # config
                self.__stop_loss_point_st = self.__stop_loss_point  # self.curr_trade.open_price + 0.5 * self.big_atr
                # self.stop_loss_point = self.curr_trade.open_price + 0.5 * self.big_atr
        else:
            if new_extremum.price < self.__stop_loss_point:
                self.__stop_loss_point = new_extremum.price - 0.25 * self.__small_atr  # max(new_extremum.price, (self.small_candle.close - 1.5 * self.big_atr))
                self.__stop_loss_point_st = self.__stop_loss_point  # self.curr_trade.open_price - 0.5 * self.big_atr
                # self.stop_loss_point = self.curr_trade.open_price - 0.5 * self.big_atr

    def update_last_small_min(self, new_min):
        """
        :param Extremum new_min:
        """
        self.__last_small_min = new_min.price

    def update_last_small_max(self, new_max):
        """
        :param Extremum new_max:
        """
        self.__last_small_max = new_max.price

    def __analyze_closing_conditions(self):
        """
        Some algorithms don't need this method
        :return:
        :rtype: MarketAnalysis or None
        """
        return None

    def __make_decision_to_close_order(self, candle_1m=None,
                                       market_analysis=None):
        """
        It is extra decision making than SL or TP
        Some algorithms don't need this method
        :return:
        :rtype: Decision or None
        """
        return None

        # if self.__meet_stop_loss(candle_1m):  # todo (1) this should be done by market(or its simulator)
        #     self.__handle_trade_closing(candle_1m, self.stop_loss_point)
        # elif self.__meet_full_close_point(
        #         candle_1m):  # todo (1) (probably) this should be done by market(or its simulator)
        #     self.__handle_trade_closing(candle_1m, self.__full_close_point)
        # elif self.curr_trade.half_close is False and self.__meet_half_close_point(
        #         candle_1m):  # todo (1) (probably) this should be done by market(or its simulator)
        #     self.__handle_half_closing(candle_1m, self.half_close_point)

    def __on_close_decision(self, decision):
        """
        Note: just for handle some changes in variables of the algorithm.
        The position is not necessarily closed yet.
        Some algorithms don't need this method
        :param Decision decision:
        """
        pass

    def __meet_stop_loss(self, candle_1m):
        """
        :param Candle candle_1m:
        :return:
        :rtype: bool
        """
        if self.__set_point_type == SET_POINT_SELL:
            if candle_1m.high >= self.__stop_loss_point:
                log_msg = f"Stop-loss({self.__set_point_type}): {self.__stop_loss_point} is met at {to_datetime(epoch=candle_1m.close_time)} "
                self.__logger.info(log_msg)
                print(log_msg)

                return True
        else:
            if candle_1m.low <= self.__stop_loss_point:
                log_msg = f"Stop-loss({self.__set_point_type}): {self.__stop_loss_point} is met at {to_datetime(epoch=candle_1m.close_time)} "
                self.__logger.info(log_msg)
                print(log_msg)

                return True
        return False

    def __handle_trade_closing(self, candle_1m, close_price):
        """
        :param Candle candle_1m:
        :param float close_price:
        """
        self.in_trade = False
        self.curr_trade.close_time = candle_1m.close_time
        self.curr_trade.close_price = close_price
        if self.curr_trade.side == SIDE_SELL:
            self.curr_trade.benefit += self.curr_trade.curr_volume * (
                    self.curr_trade.open_price - self.curr_trade.close_price)
        else:
            self.curr_trade.benefit += self.curr_trade.curr_volume * (
                    self.curr_trade.close_price - self.curr_trade.open_price)

        self.curr_trade.benefit_prcg = round(
            self.curr_trade.benefit * 100 / abs(self.curr_trade.open_price - self.__stop_loss_point_st)) / 100

        log_msg = f"{self.__set_point_type} trade is completely closed at {to_datetime(epoch=candle_1m.close_time)} " \
                  f"with total benefit: {self.curr_trade.benefit_prcg}%"
        self.__logger.info(log_msg)
        print(log_msg)

        self.__total_benefit += self.curr_trade.benefit
        self.__total_benefit_prcg += self.curr_trade.benefit_prcg

        self.__trades[-1] = self.curr_trade  # updating last trade in the list
        self.curr_trade = None

        # print(f"set_point({self.__set_point_type}): {self.__set_point}  is removed at "
        #       f"{to_datetime(epoch=candle_1m.close_time)} due to trade closing.")
        # self.__set_point = None  # set_point is removed on opening

    def __meet_half_close_point(self, candle_1m):
        """
        :param Candle candle_1m:
        :return:
        :rtype: bool
        """
        if self.__set_point_type == SET_POINT_SELL:
            if candle_1m.low <= self.__half_close_point:
                return True
        else:
            if candle_1m.high >= self.__half_close_point:
                return True
        return False

    def __meet_full_close_point(self, candle_1m):
        """
        :param Candle candle_1m:
        :return:
        :rtype: bool
        """
        if self.__set_point_type == SET_POINT_SELL:
            if candle_1m.low <= self.__full_close_point:
                return True
        else:
            if candle_1m.high >= self.__full_close_point:
                return True
        return False

    def __handle_half_closing(self, candle_1m, close_price):
        self.curr_trade.half_close_time = candle_1m.close_time
        self.curr_trade.half_close_price = close_price
        half_volume = 1 * self.curr_trade.curr_volume / 2  # config
        if self.curr_trade.side == SIDE_SELL:
            self.curr_trade.benefit += half_volume * (self.curr_trade.open_price - self.curr_trade.half_close_price)
        else:
            self.curr_trade.benefit += half_volume * (self.curr_trade.half_close_price - self.curr_trade.open_price)

        log_msg = f"In {self.__set_point_type} trade half_volume is closed at {to_datetime(epoch=candle_1m.close_time)} with benefit: " \
                  f"{round(self.curr_trade.benefit * 100 / abs(self.curr_trade.open_price - self.__stop_loss_point_st)) / 100}%"
        self.__logger.info(log_msg)
        print(log_msg)

        self.curr_trade.curr_volume = 1 * half_volume  # config
        self.__trades[-1] = self.curr_trade  # updating last trade in the list
        self.curr_trade.half_close = True
        self.__stop_loss_point = self.curr_trade.open_price

        log_msg = f"New stop_loss_point({self.__set_point_type}) after half_closing: {self.__stop_loss_point}"
        self.__logger.info(log_msg)
        print(log_msg)

    def create_open_order_decision(self):
        order_side = SIDE_SELL if self.__set_point_type == SET_POINT_SELL else SIDE_BUY
        order_type = Frx_ORDER_TYPE_SELL if self.__set_point_type == SET_POINT_SELL else Frx_ORDER_TYPE_BUY

        order_str = f"OrderSide: {order_side} - OrderType: {order_type} - Volume: {self.__config.default_volume} - Time: {self.__get_curr_time()}"
        self.__bale_bot.send_message(chat_id='6183990665', text=order_str)  # todo (1) get from config

        return Decision(oside=order_side, otype=order_type, otime=self.__get_curr_time(),
                        volume=self.__config.default_volume)

    def on_trade_open(self, order_side, order_type, open_time, open_price):  # todo (0) for online full version
        # self.in_trade = True
        # self.curr_trade = Trade(self.set_point_type, open_time=candle_1m.close_time, open_price=candle_1m.close)
        self.__curr_trade = Trade(order_side, order_type, open_time=open_time, open_price=open_price)
        self.__trades.append(self.__curr_trade)

        log_msg = f"New {order_type} trade is opened at {to_datetime(epoch=open_time)} with price {open_price}"
        self.__logger.info(log_msg)
        print(log_msg)

        if self.__set_point_type == SET_POINT_SELL:
            self.__half_close_point = self.__curr_trade.open_price - 2.5 * self.__large_atr  # 2 * self.curr_trade.open_price - self.stop_loss_point_st         #config
            self.__full_close_point = self.__curr_trade.open_price - 5 * self.__large_atr  # 2 * self.curr_trade.open_price - 1 * self.stop_loss_point_st # self.curr_trade.open_price - 3 * (self.stop_loss_point_st-self.curr_trade.open_price)
        else:
            self.__half_close_point = self.__curr_trade.open_price + 2.5 * self.__large_atr  # 2 * self.curr_trade.open_price - self.stop_loss_point_st
            self.__full_close_point = self.__curr_trade.open_price + 5 * self.__large_atr  # 2 * self.curr_trade.open_price - 1 * self.stop_loss_point_st # self.curr_trade.open_price + 3 * abs(self.stop_loss_point_st-self.curr_trade.open_price)

        self.__curr_trade.extremum = self.__extremum_before_sp

    def __get_candle_1m(self):
        """
        :return:
        :rtype: finance.models.candles.Candle
        """
        return common.df_candle_to_obj_candle(self.__hist_1m_df.iloc[-1], KLINE_INTERVAL_1MINUTE)

    def __get_curr_time(self):
        return self.__hist_1m_df.iloc[-1].close_time + 1

    @staticmethod
    def __decision_to_msg(mode, decision=None, market_analysis=None):
        return "{ Mode: " + mode + "\n Decision: {" + (decision.__str__() if decision is not None else "None") + \
               "}\n MarketAnalysis: " + \
               jsonpickle.encode(market_analysis, unpicklable=False) + " }"


class SetPoint:
    def __init__(self, extremum, sp_type, value, time):
        self.extremum = extremum
        self.type = sp_type
        self.value = value
        self.time = time


class TradeDC(Trade):
    def __init__(self, trade_side, trade_type, open_time, open_price):
        super().__init__(trade_side, trade_type, open_time, open_price)
        self.half_close = False
        self.half_close_time = None
        self.half_close_price = None
        self.extremum = None


class MarketAnalysis:
    def __init__(self, open_ready=False, close_ready=False):
        self.open_ready = open_ready
        self.close_ready = close_ready


# --- Config Section ---
class DecisionConfigDC:
    """
    :type small_interval: str
    :type large_interval: str
    :type default_volume: float
    :type buy_trade: bool
    :type sell_trade: bool
    :type bale_bot_config: finance.binance.config.BaleBotConfig
    :type mpqueue_config: finance.binance.config.MPQueueConfig
    :type log_file: str
    """

    def __init__(self, small_interval, large_interval, default_volume, buy_trade, sell_trade,
                 bale_bot_config, mpqueue_config, log_file):
        self.small_interval = small_interval
        self.large_interval = large_interval
        self.default_volume = default_volume
        self.buy_trade = buy_trade
        self.sell_trade = sell_trade
        self.bale_bot_config = bale_bot_config
        self.mpqueue_config = mpqueue_config
        self.log_file = log_file
