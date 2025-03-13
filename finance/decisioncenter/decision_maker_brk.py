import jsonpickle
import pandas as pd
from binance.enums import KLINE_INTERVAL_4HOUR

from finance.analysis.trendstate.trend_state_brk import TrendState
from finance.decisioncenter.decision import Decision
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.ufinance import common
from finance.market.trade_state_brk import TradeState
from finance.utilities import ump


class DecisionMaker:
    # todo (1): on manually market change
    # TrendState
    """
    :type __config: DecisionConfigBrk
    :type __buy_decision_status: BuyDecisionStatus
    :type __sell_decision_status: SellDecisionStatus
    :type __bale_bot: BaleBot or None
    :type __hist_1m_df_queue: multiprocessing.Queue
    :type __trend_state_queue: multiprocessing.Queue
    :type __trade_state_queue: multiprocessing.Queue
    :type __trend_state: TrendState or None
    :type __trade_state: TradeState or None
    :type __decision_queue: multiprocessing.Queue
    :type __hist_1m_df: pd.DataFrame or None
    :type __break_status: BreakStatus
    """

    def __init__(self, config, hist_1m_df_queue,
                 trend_state_queue, trade_state_queue, decision_queue, exe_mode):
        self.__config = config
        self.__buy_decision_status = BuyDecisionStatus()
        self.__sell_decision_status = SellDecisionStatus()

        self.__auto_market_dir_detection = True  # todo (2): config and runtime set
        self.__market_dir = 0  # todo (2) config

        self.__bale_bot = BaleBot(token=self.__config.bale_bot_config.token,
                                  base_url=self.__config.bale_bot_config.base_url)
        self.__chat_id = self.__config.bale_bot_config.decision_chat_id

        self.__hist_1m_df_queue = hist_1m_df_queue
        self.__trend_state_queue = trend_state_queue
        self.__trade_state_queue = trade_state_queue

        self.__trade_state = None
        self.__trend_state = None
        self.__decision_queue = decision_queue
        self.__exe_mode = exe_mode

        self.__hist_1m_df = None

        self.__open_decision_pause = 0

        self.__break_status = BreakStatus()

        self.bale_bot = BaleBot(token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')  # todo (1) get from config


    def start(self):
        # while not shutdown_event.is_set():
        while True:

            # It was hist_1m_queue before, # See issue #412
            data = ump.get_from_queue(self.__hist_1m_df_queue, timeout=self.__config.mpqueue_config.timeout)
            # print(f"DM: get hist - {self.__hist_1m_df_queue.qsize()}")
            self.__trend_state = ump.get_from_queue(self.__trend_state_queue,
                                                    timeout=self.__config.mpqueue_config.timeout)
            # print(f"DM: get trend - {self.__trend_state_queue.qsize()}")
            self.__trade_state = ump.get_from_queue(self.__trade_state_queue,
                                                    timeout=self.__config.mpqueue_config.timeout)
            # print(f"DM: get trade - {self.__trade_state_queue.qsize()}")

            self.__hist_1m_df = data  # todo why it is not directly assigned from the queue

            # tmp:
            h1_size = self.__hist_1m_df_queue.qsize()
            trend_size = self.__trend_state_queue.qsize()
            trade_size = self.__trade_state_queue.qsize()
            if h1_size != trend_size or trade_size != trade_size or h1_size != trade_size:
                print(f"HSize:{h1_size} -- TrendSize={trend_size} -- TradeSize={trade_size}")
            # tmp end

            self.__on_data_provider_update()
            # except Exception as ex:
            #     print(ex)

    def __on_data_provider_update(self):
        # print("DM: on_data_provider_update")
        # --- Updating Critical Info ---
        self.__update_open_decision_pause()
        self.__update_break_status(self.__config.general_config.brk_in_use)
        self.__handle_change_in_break_status()
        self.__handle_heavy_price_change()
        # --- End of Updating Critical Info ---

        if self.__exist_an_open_trade():  # decide to close
            market_analysis = self.__analyze_closing_conditions()
            decision = self.__make_decision_to_close_order(market_analysis)
            self.__on_close_decision(decision)
            self.__send_decision_and_market_analysis("Close", decision, market_analysis)
        else:  # decide to open
            market_analysis = self.__analyze_opening_conditions()
            decision = self.__make_decision_to_open_order(market_analysis)
            self.__send_decision_and_market_analysis("Open", decision, market_analysis)

    def __update_open_decision_pause(self):
        if self.__open_decision_pause > 0:  # decision_pause is only used for opening
            self.__open_decision_pause -= 1

    def __handle_change_in_break_status(self):
        if self.__break_status.is_new():
            if self.__break_status.dir() == 1:  # upward breaking
                self.__buy_decision_status.brk = True
                self.__buy_decision_status.ready = False
                self.__open_decision_pause = max(self.__config.general_config.pause_on_brk, self.__open_decision_pause)

                self.__sell_decision_status.brk = False
                self.__sell_decision_status.ready = False
                # print('Stopping sell_on_break if it is active')  # todo (3) no need to check ema553_dir like in sell?
            elif self.__break_status.dir() == -1:  # downward breaking
                self.__sell_decision_status.brk = True
                self.__sell_decision_status.ready = False
                self.__open_decision_pause = max(self.__config.general_config.pause_on_brk, self.__open_decision_pause)

                self.__buy_decision_status.brk = False
                self.__buy_decision_status.ready = False

    def __handle_heavy_price_change(self):
        # -- Checking Heavy increase or drop in price --
        close_prices = common.get_df_hist_field_data(self.__hist_1m_df, 'close')
        heavy_interval = self.__config.general_config.heavy_interval
        # heavy increase # -1-5 as end-5 in matlab:
        if close_prices.iloc[-1] - close_prices.iloc[-1 - heavy_interval] > self.__config.general_config.heavy_increase:
            self.__buy_decision_status.ready = False
            self.__sell_decision_status.ready = False
            self.__open_decision_pause = max(self.__config.general_config.pause_on_heavy_price,
                                             self.__open_decision_pause)
        # heavy drop:
        elif close_prices.iloc[-1] - close_prices.iloc[-1 - heavy_interval] < self.__config.general_config.heavy_drop:
            self.__buy_decision_status.ready = False
            self.__sell_decision_status.ready = False
            self.__open_decision_pause = max(self.__config.general_config.pause_on_heavy_price,
                                             self.__open_decision_pause)

    # todo (4): IMP not used: (probably for future to be set directly by admin)
    def set_buy_opening_config(self, boc):
        self.__config.buy_opening_config = boc

    def set_sell_opening_config(self, soc):
        self.__config.sell_opening_config = soc

    # end of not used

    def __exist_an_open_trade(self):
        return self.__trade_state.exist_an_open_trade()

    def __analyze_opening_conditions(self):
        """
        :return:
        :rtype: MarketAnalysis
        """
        # print("DM: analyze_opening_conditions")

        self.__update_market_dir()  # 1:upward, -1:downward, 0: is not decidable

        # todo (2): in one method
        market_analysis = MarketAnalysis()  # todo (1), need always a new object be created?
        market_analysis.set_market_dir(self.__market_dir)
        market_analysis.curr_price = self.__get_curr_close_price()
        market_analysis.time = self.__get_curr_time()

        if self.__market_dir == 1:
            self.__update_decision_status()
            if self.__buy_decision_status.ready:
                obc = self.__verify_buy_opening_conditions()
                market_analysis.set_buy_opening_conditions(obc)
        elif self.__market_dir == -1:
            self.__update_decision_status()
            if self.__sell_decision_status.ready:
                osc = self.__verify_sell_opening_conditions()
                market_analysis.set_sell_opening_conditions(osc)

        # both probably are updated:
        market_analysis.set_buy_decision_status(self.__buy_decision_status)
        market_analysis.set_sell_decision_status(self.__sell_decision_status)

        return market_analysis

    def __update_break_status(self, brk_config_name):
        """
        :param brk_config_name:
        """
        # Breaking dir is new for trend_state until next tick, but for DM it is new only in the first seen
        brk_dir = self.__trend_state.get_new_breaking_dir(brk_config_name)
        brk_hline = self.__trend_state.get_broken_sline(brk_config_name)
        self.__break_status.update(brk_hline, brk_dir)

    def __update_market_dir(self):  # todo (3) IMP: use more parameters to decide
        if self.__auto_market_dir_detection:
            if self.__break_status.dir() != 0:  # todo (1): IMP, if it is zero we currently don't change the market dir
                self.__market_dir = self.__break_status.dir()
        else:
            print("Trying to auto update market_dir in manual mode.")

    def set_auto_market_dir_detection(self, auto):
        """
        :param int auto:
        """
        self.__auto_market_dir_detection = auto

    def set_market_dir(self, market_dir):
        """
        :param int market_dir:
        """
        if not self.__auto_market_dir_detection:
            self.__market_dir = market_dir
        else:
            print("Trying to manually set market_dir in auto mode.")

    def __update_decision_status(self):

        # --- Updating Secondary Info ---
        ema45 = self.__trend_state.get_ema('9*5')  # ema92 in matlab
        ema825 = self.__trend_state.get_ema('55*15')  # ema553 in matlab
        self.__buy_decision_status.last_diff = ema45[-1] - ema825[-1]
        self.__sell_decision_status.last_diff = ema45[-1] - ema825[-1]  # todo (4) not used in sell

        new_diff = ema45[-1] - ema825[-1]
        #  --- End of Updating Secondary Info ---

        #  --- Check to Be Ready for Opening a Trade ---
        if self.__open_decision_pause == 0:
            if self.__buy_decision_status.brk:  # There was a break before pause get zero
                self.__buy_decision_status.ready = False  # temporarily prevents to buy
            elif self.__sell_decision_status.brk:  # There was a break before pause get zero
                self.__sell_decision_status.ready = True

    def __verify_buy_opening_conditions(self):
        """
        :return:
        :rtype: BuyOpeningConditions
        """
        ema825 = self.__trend_state.get_ema('55*15')
        ema300 = self.__trend_state.get_ema('20*15')
        ema135 = self.__trend_state.get_ema('9*15')
        ema275 = self.__trend_state.get_ema('55*5')
        ema100 = self.__trend_state.get_ema('20*5')
        ema45 = self.__trend_state.get_ema('9*5')

        boc = BuyOpeningConditions()
        if common.find_candle_color(self.__trend_state.get_last_candle(KLINE_INTERVAL_4HOUR)) == 1:
            boc.green_candle = True
        if ema45[-1] - ema825[-1] > self.__config.buy_opening_config.ema45_ema825_min_dif:
            boc.ema45_ema825_min_dif = True
        if abs(ema45[-1] - ema135[-1]) < self.__config.buy_opening_config.ema45_ema135_cls:
            boc.closeness_45_135 = True
        if abs(ema45[-1] - ema100[-1]) < self.__config.buy_opening_config.ema45_ema100_cls:
            boc.closeness_45_100 = True
        if abs(ema45[-1] - ema300[-1]) < self.__config.buy_opening_config.ema45_ema300_cls:
            boc.closeness_45_300 = True
        if abs(ema45[-1] - ema275[-1]) < self.__config.buy_opening_config.ema45_ema275_cls:
            boc.closeness_45_275 = True
        return boc

    def __verify_sell_opening_conditions(self):
        """
        :return:
        :rtype: SellOpeningConditions
        """
        # print("DM: verify_sell_opening_conditions")
        ema825 = self.__trend_state.get_ema('55*15')
        ema300 = self.__trend_state.get_ema('20*15')
        ema135 = self.__trend_state.get_ema('9*15')
        ema275 = self.__trend_state.get_ema('55*5')
        ema100 = self.__trend_state.get_ema('20*5')
        ema45 = self.__trend_state.get_ema('9*5')

        soc = SellOpeningConditions()
        if common.find_candle_color(self.__trend_state.get_last_candle(KLINE_INTERVAL_4HOUR)) == -1:  # red candle
            soc.red_candle = True
        if ema825[-1] - ema45[-1] > self.__config.sell_opening_config.ema825_ema45_min_dif:
            soc.ema_825_45_min_dif = True
        if ema825[-1] - ema45[-1] < self.__config.sell_opening_config.ema825_ema45_max_dif:
            soc.ema_825_45_max_dif = True
        if abs(ema45[-1] - ema135[-1]) < self.__config.sell_opening_config.ema45_ema135_cls:
            soc.closeness_45_135 = True
        if abs(ema45[-1] - ema100[-1]) < self.__config.sell_opening_config.ema45_ema100_cls:
            soc.closeness_45_100 = True
        if abs(ema45[-1] - ema300[-1]) < self.__config.sell_opening_config.ema45_ema300_cls:
            soc.closeness_45_300 = True
        if abs(ema45[-1] - ema275[-1]) < self.__config.sell_opening_config.ema45_ema275_cls:
            soc.closeness_45_275 = True

        # todo (4) in a method:
        ema_comp_hline = self.__trend_state.get_ema(self.__config.sell_opening_config.ema_compare_to_hline_name)
        brk_in_use = self.__config.general_config.brk_in_use
        cls_to_next_hline = self.__config.sell_opening_config.ema_closeness_to_next_hline
        soc.closeness_to_next_hline = self.__verify_closeness_to_next_hline(ema_comp_hline[-1], brk_in_use,
                                                                            cls_to_next_hline)

        # todo (4) in a method:
        close_prices = common.get_df_hist_field_data(self.__hist_1m_df, 'close')
        ema_comp_price = self.__trend_state.get_ema(self.__config.sell_opening_config.ema_compare_to_price_name)
        interval = self.__config.sell_opening_config.ema_compare_to_price_interval
        soc.price_is_less_than_ema_for_a_while = self.__is_less_than_ema_for_a_while(close_prices, ema_comp_price,
                                                                                     interval)

        return soc

    @staticmethod
    def __is_less_than_ema_for_a_while(close_prices, ema92, interval):
        for i in range(interval):
            if ema92[-1 - i] < close_prices.iloc[-1 - i]:  # as end-i in matlab
                return False
        return True

    def __verify_closeness_to_next_hline(self, point, brk_config_name, threshold):
        """
        :param float point: point could be price or ema value
        :param str brk_config_name:
        :param float threshold:
        :return:
        :rtype: bool
        """
        next_hline = self.__trend_state.get_next_downward_line_to_be_broken(brk_config_name)
        return abs(point - next_hline) <= threshold

    def __make_decision_to_open_order(self, market_analysis):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: finance.decisioncenter.decision.Decision or None
        """
        if self.__buy_decision_status.ready == 1:
            return self.__make_decision_to_open_buy_order(market_analysis)
        elif self.__sell_decision_status.ready == 1:
            return self.__make_decision_to_open_sell_order(market_analysis)
        else:
            return None

    def __make_decision_to_open_buy_order(self, market_analysis):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: finance.decisioncenter.decision.Decision or None
        """
        if not market_analysis.buy_decision_status:
            return None
        boc = market_analysis.buy_opening_conditions

        if self.__config.buy_opening_config.check_green_candle and not boc.green_candle:
            return None
        if self.__config.buy_opening_config.check_ema45_ema825_max_dif and not boc.ema45_ema825_max_dif:
            return None
        if self.__config.buy_opening_config.check_ema45_ema825_min_dif and not boc.ema45_ema825_min_dif:
            return None
        if self.__config.buy_opening_config.check_closeness_ema45_ema135 and boc.closeness_45_135:
            return None
        if self.__config.buy_opening_config.check_closeness_ema45_ema100 and boc.closeness_45_100:
            return None
        if self.__config.buy_opening_config.check_closeness_ema45_ema300 and boc.closeness_45_300:
            return None
        if self.__config.buy_opening_config.check_closeness_ema45_ema275 and boc.closeness_45_275:
            return None
        return Decision(otype="BUY", action="OPEN", time=market_analysis.time,
                        curr_price=market_analysis.curr_price, code="NoCode")

    def __make_decision_to_open_sell_order(self, market_analysis):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: Decision or None
        """
        if not market_analysis.sell_decision_status:
            return None
        soc = market_analysis.sell_opening_conditions

        if self.__config.sell_opening_config.check_red_candle and not soc.red_candle:
            return None
        if self.__config.sell_opening_config.check_ema825_ema45_max_dif and not soc.ema_825_45_max_dif:
            return None
        if self.__config.sell_opening_config.check_ema825_ema45_min_dif and not soc.ema_825_45_min_dif:
            return None
        if self.__config.sell_opening_config.check_closeness_ema45_ema135 and soc.closeness_45_135:
            return None
        if self.__config.sell_opening_config.check_closeness_ema45_ema100 and soc.closeness_45_100:
            return None
        if self.__config.sell_opening_config.check_closeness_ema45_ema300 and soc.closeness_45_300:
            return None
        if self.__config.sell_opening_config.check_closeness_ema45_ema275 and soc.closeness_45_275:
            return None
        if self.__config.sell_opening_config.check_ema_closeness_to_next_hline and soc.closeness_to_next_hline:
            return None
        if self.__config.sell_opening_config.check_price_is_less_than_ema_for_a_while and \
                not soc.price_is_less_than_ema_for_a_while:
            return None
        return Decision(otype="SELL", action="OPEN", time=market_analysis.time,
                        curr_price=market_analysis.curr_price, code="NoCode")

    def __send_decision_and_market_analysis(self, mode, decision, market_analysis):
        msg = "{ Mode: " + mode + "\n Decision: {" + (decision.__str__() if decision else "None") + \
              "}\n MarketAnalysis: " + \
              jsonpickle.encode(market_analysis, unpicklable=False) + " }"
        # self.__bale_bot.send(msg=msg, chat_id=self.__chat_id)
        self.__decision_queue.put(decision)

    def __analyze_closing_conditions(self):
        """
        :return:
        :rtype: MarketAnalysis
        """
        market_analysis = MarketAnalysis()
        market_analysis.set_market_dir(self.__market_dir)  # just for log
        market_analysis.curr_price = self.__get_curr_close_price()
        market_analysis.time = self.__get_curr_time()

        if self.__trade_state.get_order_type() == "BUY":  # todo (2) enum
            bcc = self.__verify_buy_closing_conditions()
            market_analysis.set_buy_closing_conditions(bcc)
        else:
            scc = self.__verify_sell_closing_conditions()
            market_analysis.set_sell_closing_conditions(scc)

        return market_analysis

    def __verify_buy_closing_conditions(self):
        """
        :return:
        :rtype: BuyClosingConditions
        """
        curr_profit = self.__trade_state.curr_profit
        ema275 = self.__trend_state.get_ema('55*5')
        ema100 = self.__trend_state.get_ema('20*5')
        ema45 = self.__trend_state.get_ema('9*5')

        bcc = BuyClosingConditions()
        if self.__trade_state.touching_hard_stop_limit:
            bcc.touching_hard_stop_limit = True
        if self.__trade_state.reaching_min_profit_deadline:
            if not self.__trade_state.touching_min_profit_before_deadline:
                if curr_profit > 0:
                    bcc.first_profit_after_deadline = True
        if self.__trade_state.touching_profit_ceiling:
            if curr_profit < self.__trade_state.get_profit_ceiling() - \
                    self.__trade_state.get_max_loss_after_touching_profit_ceiling():
                bcc.max_loss_after_touching_profit_ceiling = True
            if ema45[-1] <= ema275[-1]:
                bcc.ema_45_touching_275_after_profit_max = True
        elif ema45[-1] <= ema100[-1]:
            bcc.ema_45_touching_100_before_touching_profit_ceiling = True
        elif self.__trade_state.touching_adaptive_stop_limit:
            bcc.touching_adaptive_stop_limit = True

        return bcc

    def __verify_sell_closing_conditions(self):
        """
        :return:
        :rtype: SellClosingConditions
        """
        curr_profit = self.__trade_state.curr_profit
        ema275 = self.__trend_state.get_ema('55*5')
        ema100 = self.__trend_state.get_ema('20*5')
        ema45 = self.__trend_state.get_ema('9*5')

        scc = SellClosingConditions()
        if self.__trade_state.touching_hard_stop_limit:  # todo (1) config, who should have it?
            scc.touching_hard_stop_limit = True
        if self.__trade_state.reaching_min_profit_deadline:
            if not self.__trade_state.touching_min_profit_before_deadline:
                if curr_profit > 0:
                    scc.first_profit_after_deadline = True
        if self.__trade_state.touching_profit_ceiling:
            if curr_profit < self.__trade_state.get_profit_ceiling() - \
                    self.__trade_state.get_max_loss_after_touching_profit_ceiling():
                scc.max_loss_after_touching_profit_ceiling = True
            if ema45[-1] >= ema275[-1]:
                scc.ema_45_touching_275_after_profit_max = True
        elif ema45[-1] >= ema100[-1]:
            scc.ema_45_touching_100_before_touching_profit_ceiling = True
        elif self.__trade_state.touching_adaptive_stop_limit:
            scc.touching_adaptive_stop_limit = True

        return scc

    def __make_decision_to_close_order(self, market_analysis):  # todo (3): rethink to reform call stack
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: Decision or None
        """
        if self.__trade_state.get_order_type() == "BUY":
            return self.__make_decision_to_close_buy_order(market_analysis)
        elif self.__trade_state.get_order_type() == "SELL":
            return self.__make_decision_to_close_sell_order(market_analysis)
        else:
            return None  # expected to be unreachable

    def __make_decision_to_close_buy_order(self, market_analysis):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: Decision or None
        """
        bcc = market_analysis.buy_closing_conditions
        close_code = None
        if self.__config.buy_closing_config.check_max_loss_after_touching_profit_ceiling and \
                bcc.max_loss_after_touching_profit_ceiling:
            close_code = "201"
        elif self.__config.buy_closing_config.check_touching_hard_stop_limit and bcc.touching_hard_stop_limit:
            close_code = "202"
        elif self.__config.buy_closing_config.check_touching_adaptive_stop_limit and bcc.touching_adaptive_stop_limit:
            close_code = "203"
        elif self.__config.buy_closing_config.check_first_profit_after_deadline and bcc.first_profit_after_deadline:
            close_code = "204"
        elif self.__config.buy_closing_config.check_ema_45_touching_100_before_touching_profit_ceiling and \
                bcc.ema_45_touching_100_before_touching_profit_ceiling:
            close_code = "204"
        elif self.__config.buy_closing_config.check_ema_45_touching_275_after_touching_profit_ceiling and \
                bcc.ema_45_touching_275_after_touching_profit_ceiling:
            close_code = "205"
        if close_code is not None:
            return Decision(otype="BUY", action="CLOSE", time=market_analysis.time,
                            curr_price=market_analysis.curr_price, code=close_code)
        return None

    def __make_decision_to_close_sell_order(self, market_analysis):
        """
        :param MarketAnalysis market_analysis:
        :return:
        :rtype: Decision or None
        """
        scc = market_analysis.sell_closing_conditions
        close_code = None
        if self.__config.sell_closing_config.check_max_loss_after_touching_profit_ceiling and \
                scc.max_loss_after_touching_profit_ceiling:
            close_code = "-201"
        if self.__config.sell_closing_config.check_touching_hard_stop_limit and scc.touching_hard_stop_limit:
            close_code = "-202"
        if self.__config.sell_closing_config.check_touching_adaptive_stop_limit and scc.touching_adaptive_stop_limit:
            close_code = "-203"
        if self.__config.sell_closing_config.check_first_profit_after_deadline and scc.first_profit_after_deadline:
            close_code = "-204"
        if self.__config.sell_closing_config.check_ema_45_touching_100_before_touching_profit_ceiling and \
                scc.ema_45_touching_100_before_touching_profit_ceiling:
            close_code = "-205"
        if self.__config.sell_closing_config.check_ema_45_touching_275_after_touching_profit_ceiling and \
                scc.ema_45_touching_275_after_touching_profit_ceiling:
            close_code = "-206"
        if close_code is not None:
            return Decision(otype="SELL", action="CLOSE", time=market_analysis.time,
                            curr_price=market_analysis.curr_price, code=close_code)
        return None

    def __get_curr_close_price(self):
        return self.__hist_1m_df.iloc[-1].close

    def __get_curr_time(self):
        return self.__hist_1m_df.iloc[-1].close_time

    def __on_close_decision(self, decision):
        """
        :param Decision decision:
        """
        if decision is not None:
            self.__buy_decision_status.ready = False
            self.__sell_decision_status.ready = False
            self.__open_decision_pause = max(self.__config.general_config.pause_on_close, self.__open_decision_pause)


class BuyOpeningConditions:
    def __init__(self):
        self.green_candle = False
        self.ema45_ema825_max_dif = False  # not used
        self.ema45_ema825_min_dif = False
        self.closeness_45_135 = False
        self.closeness_45_100 = False
        self.closeness_45_300 = False
        self.closeness_45_275 = False


class SellOpeningConditions:

    def __init__(self):
        self.red_candle = False
        self.ema_825_45_max_dif = False
        self.ema_825_45_min_dif = False
        self.closeness_45_135 = False
        self.closeness_45_100 = False
        self.closeness_45_300 = False
        self.closeness_45_275 = False
        self.closeness_to_next_hline = False  # todo (4) not used in buy
        self.price_is_less_than_ema_for_a_while = False  # todo (4) not used in buy


class BuyClosingConditions:
    def __init__(self):
        self.max_loss_after_touching_profit_ceiling = False
        self.ema_45_touching_275_after_touching_profit_ceiling = False
        self.ema_45_touching_100_before_touching_profit_ceiling = False
        self.first_profit_after_deadline = False
        self.touching_adaptive_stop_limit = False
        self.touching_hard_stop_limit = False


class SellClosingConditions:
    def __init__(self):
        self.max_loss_after_touching_profit_ceiling = False
        self.ema_45_touching_275_after_touching_profit_ceiling = False
        self.ema_45_touching_100_before_touching_profit_ceiling = False
        self.first_profit_after_deadline = False
        self.touching_adaptive_stop_limit = False
        self.touching_hard_stop_limit = False


class BuyDecisionStatus:
    def __init__(self):
        self.brk = False  # False: no break, True: break (not necessarily is new)
        self.ready = False
        self.last_ema_diff = 0  # todo (3): rename  # todo: out of this class?  # todo: init value?
        self.touching_profit_ceiling = 0  # todo (3): out of this class?
        self.close_on_first_profit = 0  # todo (3): out of this class?


class SellDecisionStatus:
    def __init__(self):
        self.brk = False  # False: no break, True: break (not necessarily is new)
        self.ready = False
        self.last_ema_diff = 0  # todo (3): rename  # todo: init value?
        self.touching_profit_ceiling = 0  # todo (3): out of this class?
        self.close_on_first_profit = 0  # todo (3): out of this class?


class MarketAnalysis:
    """  # todo :var could be removed (only is needed for documentation)
    :type market_dir: int
    :type curr_price: float
    :type time: str or None

    :var BuyDecisionStatus buy_decision_status:
    :type buy_decision_status: BuyDecisionStatus or None

    :var BuyOpeningConditions buy_opening_conditions:
    :type buy_opening_conditions: BuyOpeningConditions or None

    :var BuyClosingConditions buy_closing_conditions:
    :type buy_closing_conditions: BuyClosingConditions or None

    :var SellDecisionStatus sell_decision_status:
    :type sell_decision_status: SellDecisionStatus or None

    :var SellOpeningConditions sell_opening_conditions:
    :type sell_opening_conditions: SellOpeningConditions or None

    :var SellClosingConditions sell_closing_conditions:
    :type sell_closing_conditions: SellClosingConditions or None
    """

    def __init__(self):
        self.market_dir = 0
        self.curr_price = 0
        self.time = None
        self.buy_decision_status = None
        self.buy_opening_conditions = None
        self.buy_closing_conditions = None
        self.sell_decision_status = None
        self.sell_opening_conditions = None
        self.sell_closing_conditions = None

        # todo IMP remove set methods

    def set_market_dir(self, market_dir):
        self.market_dir = market_dir

    def set_buy_decision_status(self, bds):
        self.buy_decision_status = bds

    def set_buy_opening_conditions(self, boc):
        self.buy_opening_conditions = boc

    def set_buy_closing_conditions(self, bcc):
        self.buy_closing_conditions = bcc

    def set_sell_decision_status(self, sds):
        self.sell_decision_status = sds

    def set_sell_opening_conditions(self, soc):
        self.sell_opening_conditions = soc

    def set_sell_closing_conditions(self, scc):
        self.sell_closing_conditions = scc


class BreakStatus:
    def __init__(self):
        self.__hline = 0
        self.__dir = 0
        self.__seen = False  # it is seen and considered by DM

    def update(self, hline, dir_):
        """
        :param float hline:
        :param dir dir_: -1, 0, 1
        """
        if abs(hline - self.__hline) <= 0.0001:  # todo: in math utility
            self.__seen = True
        else:
            self.__hline = hline
            self.__dir = dir_
            self.__seen = False

    def is_new(self):
        """
        It is considered as new if it has not been seen by DM
        :return:
        :rtype: bool
        """
        return not self.__seen

    def dir(self):
        """
        :return:
        :rtype: int
        """
        return self.__dir


# --- Config Section ---

class DecisionConfigBrk:
    """
    :type general_config: TradeDecisionGeneralConfig
    :type buy_opening_config: BuyOpeningConfig
    :type sell_opening_config: SellOpeningConfig
    :type buy_closing_config: BuyClosingConfig
    :type sell_closing_config: SellClosingConfig
    :type bale_bot_config: finance.binance.config.BaleBotConfig
    :type mpqueue_config: finance.binance.config.MPQueueConfig
    :
    """
    def __init__(self, general_config, buy_opening_config, sell_opening_config, buy_closing_config,
                 sell_closing_config, bale_bot_config, mpqueue_config):
        self.general_config = general_config
        self.buy_opening_config = buy_opening_config
        self.sell_opening_config = sell_opening_config
        self.buy_closing_config = buy_closing_config
        self.sell_closing_config = sell_closing_config
        self.bale_bot_config = bale_bot_config
        self.mpqueue_config = mpqueue_config


class TradeDecisionGeneralConfig:
    """
    :type pause_on_close: int
    :type pause_on_heavy_price: int
    :type pause_on_brk: int
    :type active_brk_name: str
    :type auto_market_dir: bool
    :type heavy_increase: int
    :type heavy_drop: int
    :type heavy_interval: int
    """

    def __init__(self, pause_on_close, pause_on_hp, pause_on_brk, active_brk_name,
                 auto_market_dir, heavy_increase, heavy_drop, heavy_interval):
        self.pause_on_close = pause_on_close
        self.pause_on_heavy_price = pause_on_hp
        self.pause_on_brk = pause_on_brk
        self.brk_in_use = active_brk_name
        self.auto_market_dir = auto_market_dir
        self.heavy_increase = heavy_increase
        self.heavy_drop = heavy_drop
        self.heavy_interval = heavy_interval


class BuyOpeningConfig:
    def __init__(self, check_green_candle, check_ema45_ema825_min_dif, check_ema45_ema825_max_dif,
                 check_closeness_ema45_ema135, check_closeness_ema45_ema100, check_closeness_ema45_ema300,
                 check_closeness_ema45_ema275, ema45_ema825_min_dif, ema45_ema135_cls, ema45_ema100_cls,
                 ema45_ema300_cls, ema45_ema275_cls):
        self.check_green_candle = check_green_candle
        self.check_ema45_ema825_min_dif = check_ema45_ema825_min_dif
        # todo (4) unused:
        self.check_ema45_ema825_max_dif = check_ema45_ema825_max_dif
        self.check_closeness_ema45_ema135 = check_closeness_ema45_ema135
        self.check_closeness_ema45_ema100 = check_closeness_ema45_ema100
        self.check_closeness_ema45_ema300 = check_closeness_ema45_ema300
        self.check_closeness_ema45_ema275 = check_closeness_ema45_ema275

        self.ema45_ema825_min_dif = ema45_ema825_min_dif
        self.ema45_ema135_cls = ema45_ema135_cls
        self.ema45_ema100_cls = ema45_ema100_cls
        self.ema45_ema300_cls = ema45_ema300_cls
        self.ema45_ema275_cls = ema45_ema275_cls


class SellOpeningConfig:
    def __init__(self, check_red_candle, check_ema825_ema45_min_dif, check_ema825_ema45_max_dif,
                 check_closeness_ema45_ema135, check_closeness_ema45_ema100, check_closeness_ema45_ema300,
                 check_closeness_ema45_ema275, check_ema_closeness_to_next_hline,
                 check_price_is_less_than_ema_for_a_while, ema825_ema45_min_dif, ema825_ema45_max_dif,
                 ema45_ema135_cls, ema45_ema100_cls, ema45_ema300_cls, ema45_ema275_cls, ema_compare_to_hline_name,
                 ema_closeness_to_next_hline, ema_compare_to_price_name, ema_compare_to_price_interval):
        self.check_red_candle = check_red_candle
        self.check_ema825_ema45_min_dif = check_ema825_ema45_min_dif
        self.check_ema825_ema45_max_dif = check_ema825_ema45_max_dif
        self.check_closeness_ema45_ema135 = check_closeness_ema45_ema135
        self.check_closeness_ema45_ema100 = check_closeness_ema45_ema100
        self.check_closeness_ema45_ema300 = check_closeness_ema45_ema300
        self.check_closeness_ema45_ema275 = check_closeness_ema45_ema275
        # todo (4) not used in buy:
        self.check_ema_closeness_to_next_hline = check_ema_closeness_to_next_hline
        # todo (4) not used in buy:
        self.check_price_is_less_than_ema_for_a_while = check_price_is_less_than_ema_for_a_while

        self.ema825_ema45_min_dif = ema825_ema45_min_dif
        self.ema825_ema45_max_dif = ema825_ema45_max_dif
        self.ema45_ema135_cls = ema45_ema135_cls
        self.ema45_ema100_cls = ema45_ema100_cls
        self.ema45_ema300_cls = ema45_ema300_cls
        self.ema45_ema275_cls = ema45_ema275_cls

        self.ema_compare_to_hline_name = ema_compare_to_hline_name
        self.ema_closeness_to_next_hline = ema_closeness_to_next_hline
        self.ema_compare_to_price_name = ema_compare_to_price_name
        self.ema_compare_to_price_interval = ema_compare_to_price_interval


class BuyClosingConfig:
    def __init__(self, check_max_loss_after_touching_profit_ceiling,
                 check_ema_45_touching_275_after_touching_profit_ceiling,
                 check_ema_45_touching_100_before_touching_profit_ceiling,
                 check_first_profit_after_deadline, check_touching_adaptive_stop_limit,
                 check_touching_hard_stop_limit):
        self.check_max_loss_after_touching_profit_ceiling = check_max_loss_after_touching_profit_ceiling
        self.check_ema_45_touching_275_after_touching_profit_ceiling = \
            check_ema_45_touching_275_after_touching_profit_ceiling
        self.check_ema_45_touching_100_before_touching_profit_ceiling = \
            check_ema_45_touching_100_before_touching_profit_ceiling
        self.check_first_profit_after_deadline = check_first_profit_after_deadline
        self.check_touching_adaptive_stop_limit = check_touching_adaptive_stop_limit
        self.check_touching_hard_stop_limit = check_touching_hard_stop_limit


class SellClosingConfig:
    def __init__(self, check_max_loss_after_touching_profit_ceiling,
                 check_ema_45_touching_275_after_touching_profit_ceiling,
                 check_ema_45_touching_100_before_touching_profit_ceiling,
                 check_first_profit_after_deadline, check_touching_adaptive_stop_limit,
                 check_touching_hard_stop_limit):
        self.check_max_loss_after_touching_profit_ceiling = check_max_loss_after_touching_profit_ceiling
        self.check_ema_45_touching_275_after_touching_profit_ceiling = \
            check_ema_45_touching_275_after_touching_profit_ceiling
        self.check_ema_45_touching_100_before_touching_profit_ceiling = \
            check_ema_45_touching_100_before_touching_profit_ceiling
        self.check_first_profit_after_deadline = check_first_profit_after_deadline
        self.check_touching_adaptive_stop_limit = check_touching_adaptive_stop_limit
        self.check_touching_hard_stop_limit = check_touching_hard_stop_limit

