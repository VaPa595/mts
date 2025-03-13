import pandas as pd

from finance.analysis.trendstate.trend_state import TrendState
from finance.analysis.trendlines import trendlinebreak as tlb
from finance.analysis.trendlines.ema import EMA
from finance.analysis.trendlines.trend_lines import BreakInfo, RuntimeTrendLines
from finance.analysis.trendlines.trendlinebreak import LineBreakingStatus
# TODO (3): it results in circular dependency
# from finance.dataprovider.data_provider import InfoOnTick  # TODO (3): it results in circular dependency
from finance.models.candles import Candle
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.uio import ulog
from finance.utilities.ufinance import common
from finance.utilities.utime import TicToc

# todo (0): needs many changes similar to TrendStateDC


class TrendStateBrk(TrendState):
    # todo (3): all lines are 4h, consider others (where??????)
    """
    :type __config: TrendStateConfig
    :type __histories_lbk: list[HistoricalCandleData] or None
    """

    # todo(2) use same data structure of __histories_lbk for all hist_1m(df)
    # todo(2) check docstring of __histories_atr

    def __init__(self, config, data_provider):
        """

        :param config:
        :type config: TrendStateConfigBrk
        :param finance.dataprovider.data_provider.DataProvider data_provider:  # todo(2)  ugly
        """

        super().__init__(config, data_provider)  # todo (0) brk
        self.__config = config

        # Break line parameters
        self.__histories_lbk = None  # are based on deque[Candle]  # todo (2): think of converting to dictionary
        self.__lbk_status_list = []
        self.__runtime_trend_lines = RuntimeTrendLines()

        self.update_time = 0

        # Bale bot parameters
        self.__bale_bot = BaleBot(token=config.bale_bot_config.token, base_url=config.bale_bot_config.base_url)
        self.__break_chat_id = config.bale_bot_config.break_chat_id
        self.__ema_chat_id = config.bale_bot_config.ema_chat_id
        # self.__bale_bot = BaleBot(token='1798071945:qPHMu25WYCyotFXCsbWQRWTf3gZtF5MrqUUchth8',
        #                           base_url="https://tapi.bale.ai/")

        self.__ema_data = {}
        self.__last_candles = {}  # new, is needed by DecisionMaker

        self.__data_provider = data_provider

        self.__logger = ulog.get_default_logger(__name__, config.log_file)

        self.__tic_toc = TicToc()

    def __getstate__(self):
        # Copy the object's state from self.__dict__ which contains
        # all our instance attributes. Always use the dict.copy()
        # method to avoid modifying the original state.
        state = self.__dict__.copy()
        # Remove the un-picklable entries.
        del state['_TrendStateBrk__bale_bot']
        del state['_TrendStateBrk__runtime_trend_lines']
        del state['_TrendStateBrk__data_provider']
        del state['_TrendStateBrk__histories_lbk']
        return state

    def __setstate__(self, state):
        # Restore instance attributes (i.e., filename and lineno).
        self.__dict__.update(state)
        # Restore the previously opened file's state. To do so, we need to
        # reopen it and read from it until the line count is restored.
        self.__bale_bot = None
        self.__runtime_trend_lines = None
        self.__data_provider = None
        self.__histories_lbk = None

    def init(self, hist_1m, hist_1m_df, last_candles, candle_intervals):
        self.__init_histories_lbk()
        self.__init_trend_lines()  # should be after initializing histories
        self.__init_last_candles(last_candles)
        self.__init_ema_data(hist_1m_df)
        self.__init_all_lines_break_status(hist_1m, hist_1m_df, candle_intervals)  # it should be after init ema

    def update(self, curr_time, hist_1m_df):
        self.__update_ema_data(hist_1m_df)
        ticks = common.get_ticks(curr_time)
        if len(ticks) > 0:
            self.__on_new_ticks(ticks)

    def __on_new_ticks(self, ticks):
        self.__update_histories_lbk(ticks)  # all histories in trend_state are related to trend lines and breaking
        self.__update_trend_lines(ticks)
        self.__update_last_candles(self.__data_provider.get_last_candles(ticks))
        self.__update_lbk_status(ticks)

    def __update_lbk_status(self, ticks):
        break_info_list = self.__create_break_info_list(ticks)
        if len(break_info_list) > 0:  # todo (2) if not why it is called?
            self.update_time = break_info_list[0].candle.close_time  # all info have same close_time
            for break_info in break_info_list:
                # Note: one lbk_status for each info_on_tick
                lbk_status = self.get_lbk_status(break_info.breaking_name)
                lbk_status.verify_change_in_next_lines_to_be_broken(break_info.slines)
                lbk_status.update_line_break_status(break_info.candle, break_info.ema_dir, break_info.slines)
                # IMPORTANT: slines should be updated before
                self.__on_updating_line_breaking_status(lbk_status)

    # EMA section
    def __init_ema_data(self, hist_1m_df):
        """
        :param pd.DataFrame hist_1m_df:
        """

        for ema_config in self.__config.ema_configs:
            ema = EMA(name=ema_config.name, span=ema_config.span, field=ema_config.field,
                      dir_interval=ema_config.dir_interval, hist_df=hist_1m_df)
            self.__ema_data[ema_config.name] = ema

    def __update_ema_data(self, hist_df):
        # close_prices = common.get_df_hist_field_data(hist_df, 'close')
        # print(f"updating ema --- close[0]: {close_prices.iloc[0]} --- close[-1]: {close_prices.iloc[-1]}")
        for ema_name in self.__ema_data:
            ema = self.__ema_data[ema_name]
            ema.update(hist_df)

    def __on_updating_ema_data(self):
        pass
        msg = ''
        for ema_name in self.__ema_data:
            ema = self.__ema_data[ema_name]
            msg += ema.__str__() + '\n'
        msg += "---------------------\n"
        self.__bale_bot.send(msg, chat_id=self.__ema_chat_id)

    def get_ema(self, name):
        """
        :param str name:
        :return:
        :rtype: EMA
        """
        return self.__ema_data[name]

    # Last candle section
    def __init_last_candles(self, last_candles):
        self.__last_candles = last_candles

    def set_last_candle(self, candle_interval, last_candle):
        """
        :param str candle_interval:
        :param Candle last_candle:
        """
        self.__last_candles[candle_interval] = last_candle

    def get_last_candle(self, candle_interval):
        """
        :param str candle_interval:
        :return:
        :rtype: Candle
        """
        return self.__last_candles[candle_interval]

    def __update_last_candles(self, ticks):
        for tick in ticks:
            last_candle = self.__data_provider.get_last_candle(tick)
            self.set_last_candle(candle_interval=tick, last_candle=last_candle)

    # region Line breaking Section:

    def __init_histories_lbk(self):  # all are for trending
        self.__histories_lbk = []
        for sline_config in self.__config.slines_configs:
            hcd = self.__init_hist_lbk(sline_config)
            self.__histories_lbk.append(hcd)

    def __init_hist_lbk(self, sline_config):  # for trending
        """
        It is initiated from db
        :param StaticLineConfig sline_config:
        :return
        :rtype HistoricalCandleData
        """
        print("Initializing hist for slines: " + sline_config.name)
        start_time = sline_config.start_time
        end_time = sline_config.end_time  # if end_time is None, history up to now is loaded.
        hist = self.__data_provider.get_hist(sline_config.candle_interval, start_time=start_time, end_time=end_time)
        hcd = HistoricalCandleData(sline_config.name, sline_config.candle_interval, hist)
        return hcd

    def __init_trend_lines(self):  # IMP: should be call after initializing all histories
        for hcd in self.__histories_lbk:
            hline_config = self.__get_sline_config(hcd.name)
            self.__runtime_trend_lines.update_slines_info(hline_config, hcd.get_close_prices())
            # self.__save_hlines_info(hlines_info)  # for matlab, hlines_info = previous line
            self.__logger.debug("Initial hlines are created and saved: " + hcd.name)

    def __init_all_lines_break_status(self, hist_1m, hist_1m_df, candle_intervals):
        """
        :param deque[Candle] hist_1m:
        :param pd.DataFrame hist_1m_df:
        :param list[str] candle_intervals:
        """
        break_info_list = self.__create_break_info_list(candle_intervals)
        for break_info in break_info_list:  # Note: one lbk_status for each info_on_tick
            lbk_status = LineBreakingStatus(breaking_name=break_info.breaking_name,
                                            candle_interval=break_info.candle_interval)

            lbk_status.next_upward_line_to_be_broken, lbk_status.next_downward_line_to_be_broken = \
                tlb.find_initial_next_lines_to_be_broken(hist_1m, hist_1m_df, break_info.candle_interval,
                                                         break_info.slines,
                                                         0.6)  # todo (2) get form config
            if lbk_status.next_upward_line_to_be_broken == -1:
                raise Exception(f"Could not initialize the next lines to be broken. BreakingName ="
                                f" {break_info.breaking_name}")

            self.__lbk_status_list.append(lbk_status)

    def __update_histories_lbk(self, ticks):
        for hcd in self.__histories_lbk:
            if hcd.candle_interval in ticks:
                last_candle_in_hist = hcd.hist[-1]
                next_candle_open_time = last_candle_in_hist.close_time + 1
                next_candle = self.__data_provider.get_candle(hcd.candle_interval, next_candle_open_time)
                hcd.hist.popleft()  # removing oldest candle  (used for list or dequeue)
                hcd.hist.append(next_candle)

    def __update_trend_lines(self, ticks):
        for hcd in self.__histories_lbk:
            if hcd.candle_interval in ticks:
                sline_config = self.__get_sline_config(hcd.name)
                self.__runtime_trend_lines.update_slines_info(sline_config, hcd.get_close_prices())
                # self.__save_slines_info(slines_info)  # (for matlab) slines_info = previous line

    def __get_sline_config(self, name):  # todo (5): think of creating a class which handles defined list
        """
        :param str name:
        :return:
        :rtype: HLineConfig
        """
        for sline_config in self.__config.slines_configs:
            if sline_config.name == name:
                return sline_config
        raise Exception("Invalid sline_config")

    def __create_break_info_list(self, candle_intervals):
        """
        :param list[str] candle_intervals:
        :return:
        :rtype: list[InfoOnTick] info_list_on_last_tick:
        """
        breaking_info_list = []
        for breaking_config in self.__config.breaking_configs:
            if breaking_config.candle_interval in candle_intervals:
                candle = self.get_last_candle(breaking_config.candle_interval)

                slines_info = self.__runtime_trend_lines.get_last_slines_info(breaking_config.sline_name)

                slines = slines_info.slines
                ema = self.get_ema(breaking_config.ema_name)
                breaking_info_list.append(BreakInfo(breaking_name=breaking_config.name,
                                                    sline_name=breaking_config.sline_name,
                                                    candle_interval=breaking_config.candle_interval,
                                                    candle=candle, ema_dir=ema.dir, slines=slines))
        return breaking_info_list

    def __on_updating_line_breaking_status(self, lbk_status):  # todo (2) rename
        """
        :param LineBreakingStatus lbk_status:
        """
        self.__logger.info(f"BreakStatus: {lbk_status}")
        if lbk_status.breaking_dir != 0:  # todo (2) rename breaking to break (every where)
            # print(f"LINE-BREAK: {lbk_status}")
            self.__bale_bot.send(lbk_status.__str__(), chat_id=self.__break_chat_id)

    def get_lbk_status(self, name):
        """
        :param str name:
        :return:
        :rtype: LineBreakingStatus
        """
        for lbk_status in self.__lbk_status_list:
            if lbk_status.breaking_name == name:
                return lbk_status
        raise Exception("Invalid name for lbk_status")

    def get_lbk_status_list(self):
        return self.__lbk_status_list

    def get_next_downward_line_to_be_broken(self, name):
        """
        :param str name:
        :return:
        :rtype: float
        """
        lbk_status = self.get_lbk_status(name)
        return lbk_status.next_downward_line_to_be_broken

    def get_new_breaking_dir(self, name):
        """
        :param str name:
        :return:
        :rtype: int
        """
        lbk_status = self.get_lbk_status(name)
        if lbk_status.is_new_break:  # it is new until the next corresponding tick
            return lbk_status.breaking_dir
        else:
            return 0  # no break, or old break

    def get_broken_sline(self, name):
        """
        :param str name:
        :return:
        :rtype: float
        """
        lbk_status = self.get_lbk_status(name)
        return lbk_status.broken_line

    def __save_slines_info(self, slines_info):  # (for matlab)
        # file_abs_path = os.path.join(self.__slines_dir, slines_info.hist_name + ".json")  self.__config.slines_dir  # directory
        # ujson.write_obj_to_json_file(slines_info, file_abs_path)
        pass

    # endregion


# ---- Related Classes ----
class HistoricalCandleData:
    """
    :type name: str unique name
    :type candle_interval: str  interval of the candle: i.e. 1m, 15m, 1h, 4h
    :type hist: deque[Candle]  # todo (1) it seems better to be df
    """

    def __init__(self, name, candle_interval, hist):
        self.name = name
        self.candle_interval = candle_interval
        self.hist = hist

    def get_close_prices(self):
        result = [candle.close for candle in self.hist]  # todo (4): it imposes additional O(n) time overhead
        return result


class TrendStateConfigBrk:  # each TrendStateXXX picks its required configs
    """
    :type ema_configs: list[finance.analysis.trendlines.ema.EmaConfig] or None
    :type breaking_configs: list[finance.analysis.trendlines.trendlinebreak.LineBreakConfig] or None
    :type slines_configs: list[finance.analysis.trendlines.trendlinebreak.StaticLineConfig] or None
    :type bale_bot_config: finance.binance.config.BaleBotConfig or None
    :type log_file: str
    """

    # todo (1) handle in some configs are None
    def __init__(self, ema_configs, breaking_configs, slines_configs, bale_bot_config, log_file):
        self.ema_configs = ema_configs
        self.breaking_configs = breaking_configs
        self.slines_configs = slines_configs
        self.bale_bot_config = bale_bot_config
        self.log_file = log_file