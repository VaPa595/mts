# todo (3): make it easier to add new history for trending just by changing the config file

# todo (2): using different naming for updating db directly from dataprovider and updating with created candles
# todo: check all kind of order_by('-open_time') and validate their usage
# todo (2): uniform use of save_history_in_db, save_candles_in_db and etc.
# todo (2): make sure config file is set with valid parameters (specially start/end date of histories)
import math
import time
from collections import deque

import pandas as pd
# from binance import ThreadedWebsocketManager
from binance.enums import KLINE_INTERVAL_1MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR, KLINE_INTERVAL_15MINUTE
from mongoengine import disconnect, connect

from finance.analysis.trendstate.trend_state import TrendState
from finance.datasource.data_source import DataSource
from finance.dataprovider.data_base import DataBaseInterface
from finance.models.candles import Candle
from finance.utilities import utime
from finance.utilities.uio import ulog
from finance.utilities.ufinance import common
from finance.utilities.ufinance.common import candle_interval_in_millisecond, calc_last_tick_epoch, \
    calc_diff_two_candles, are_candles_consecutive, get_tick_times_in_interval, create_candle_from_hist_1m
from finance.utilities.utime import TicToc


# for docstring:  # todo (3): cyclic import
# from finance.dataprovider.config import SLineConfig
# from finance.dataprovider.config import BreakingConfig

# todo (3): rename all times as epoch
def num_returned_candles_by_binance(candle_interval, start_time, end_time):
    interval_as_millisecond = candle_interval_in_millisecond(candle_interval)
    first_candle_open_time = math.ceil(start_time / interval_as_millisecond) * interval_as_millisecond
    open_time_after_last_candle = (math.floor(end_time / interval_as_millisecond) + 1) * interval_as_millisecond
    num = int((open_time_after_last_candle - first_candle_open_time) / interval_as_millisecond)
    # print(f"expected history size: {num}")
    return num


def verify_size_of_required_history(candle_interval, start_time, end_time):
    interval_in_millisec = candle_interval_in_millisecond(candle_interval)
    first_open_time = math.ceil(start_time / interval_in_millisec) * interval_in_millisec
    last_open_time = math.floor(end_time / interval_in_millisec) * interval_in_millisec
    size_of_hist = (last_open_time - first_open_time) / interval_in_millisec
    print(size_of_hist)


def verify_history(history, candle_interval, start_time, end_time):
    expected_history_size = num_returned_candles_by_binance(candle_interval, start_time, end_time)
    return len(history) == expected_history_size


def update_incomplete_big_candle(incomplete_big_candle, new_candle_1m):  # used only in test mode
    """
    :param Candle incomplete_big_candle:
    :param Candle new_candle_1m:
    :return:
    :rtype: Candle
    """
    if incomplete_big_candle.high < new_candle_1m.high:
        incomplete_big_candle.high = new_candle_1m.high
    if incomplete_big_candle.low > new_candle_1m.low:
        incomplete_big_candle.low = new_candle_1m.low
    incomplete_big_candle.close = new_candle_1m.close
    incomplete_big_candle.volume = incomplete_big_candle.volume + new_candle_1m.volume
    incomplete_big_candle.close_time = new_candle_1m.close_time


def is_a_complete_candle(candle_interval, candle):  # used only in test mode
    if candle_interval == KLINE_INTERVAL_15MINUTE:
        return (candle.close_time + 1) % 900000 == 0  # 15 * 60 * 1000: millisecond
    if candle_interval == KLINE_INTERVAL_1HOUR:
        return (candle.close_time + 1) % 3600000 == 0  # 60 * 60 * 1000: millisecond
    if candle_interval == KLINE_INTERVAL_4HOUR:
        return (candle.close_time + 1) % 14400000 == 0  # 4 * 60 * 60 * 1000: millisecond
    raise Exception("Invalid candle interval")


class DataProvider:  # todo (4): separate public and private methods,  # todo (2): complete docstring
    """
    :type __config: DataProviderConfig
    :type __data_source: DataSource
    :type __hist_1m_queues: list[multiprocessing.Queue]
    :type __hist_1m_df_queues: list[multiprocessing.Queue]
    :type __trend_state_queues: list[multiprocessing.Queue]
    :type __trend_state: TrendState
    :type __hist_1m: deque[Candle] or None
    :type __hist_1m_df: pd.DataFrame or None
    :type __exe_mode: str
    :type __fast_exe_modes: list[str]
    :type __logger: logging.Logger
    """

    # todo (2) separate trend_state from DP (i.e. use something like trend_state_tracker connected with a queue to DP)
    # todo (3) find a systematic way to keep active candle_intervals (some improvements are done)
    def __init__(self, config, data_source, trend_state, hist_1m_queues, hist_1m_df_queues, trend_state_queues,
                 exe_mode, fast_exe_modes):
        """

        :param DataProviderConfig config:
        :param DataSource data_source:
        :param TrendState trend_state:
        :param list[multiprocessing.Queue] hist_1m_queues:
        :param list[multiprocessing.Queue] hist_1m_df_queues:
        :param list[multiprocessing.Queue] trend_state_queues:
        :param str exe_mode:
        :param list[str] fast_exe_modes:
        """
        self.__ready = False  # it is currently used for dropping received candles until all initializations are done.
        self.__curr_time = 0  # epoch time, it will be updated on each new candle_1m, not used before first update
        self.__config = config
        self.__candle_intervals = config.candle_intervals  # NOTE: it doesn't contain 1m  # todo (3): rename: tracking_c_i?

        self.__trend_state = trend_state

        self.__hist_1m_queues = hist_1m_queues
        self.__hist_1m_df_queues = hist_1m_df_queues
        self.__trend_state_queues = trend_state_queues

        self.__data_source = data_source

        self.__exe_mode = exe_mode
        self.__fast_exe_modes = fast_exe_modes

        self.__hist_1m = None  # under evaluation history for trading
        self.__hist_1m_df = None  # new: hist_1m as pandas.DataFrame to fast calculation of EMA (preventing hist to DF)

        self.__received_complete_candle = 0

        self.__dbi = DataBaseInterface()
        self.__dbi.init(self.__config.db_log_file)

        self.__hist_1m_days = self.__config.hist_1m_days

        self.__tic_toc = TicToc()
        self.__incomplete_big_candles = {}  # Only for db-less simulation, one key for each interval in {15m, 1h, 4h}
        self.__last_complete_big_candles = {}
        self.__logger = ulog.get_default_logger(__name__, self.__config.dp_log_file)

        self.__logger.info("DP is initialized.")

    def start(self, db_name):  # todo (0) it seems that sock simulator use this not start_test
        self.__logger.info("starting...")
        connect(db_name)
        self.__data_source.init_candle_socket()
        # Candle socket should be started first to update curr_time on receiving first candle:
        self.__logger.info("starting candle socket ...")
        self.__data_source.start_candle_socket(callback=self.__on_new_candle_1m, symbol=self.__config.symbol,
                                               candle_interval=KLINE_INTERVAL_1MINUTE)

        # self.__wait_until_next_tick_1m()  # todo (2) it seems useless
        self.__wait_for_init_curr_time()

        self.__update_db_with_requisite_histories()

        self.__tic_toc.tic()  # **

        self.__update_hist_1m_from_db()  # at this point it is initializing
        self.__init_hist_1m_df()  # should be called after initializing hist_1m

        self.__trend_state.init(self)  # it should be after initializing histories

        self.__logger.info("all prerequisite jobs are done.")

        self.__logger.info("candle socket is started.")

        self.__ready = True

        if self.__tic_toc.toc() >= 55:  # **
            print(f"Initialization took {self.__tic_toc.toc()} sec")
            self.__logger.warning(f"Initialization took {self.__tic_toc.toc()} sec")

    def stop(self):
        disconnect()  # todo (4): use db prefix
        self.__data_source.stop_candle()
        self.__logger.info("Disconnecting from db and candle socket.")

    def start_test(self, test_name, curr_time):
        connect(test_name)

        self.__curr_time = curr_time  # it is better to be close to __update_candles_db_according_to_configs  # todo (1) to the same as start(), set curr_time on first candle (__wait_for_init_curr_time, self.__ready = True)
        self.__update_db_with_requisite_histories()  # it is necessary before initializing histories.

        self.__update_hist_1m_from_db()
        self.__init_hist_1m_df()  # should be called after initializing hist_1m

        self.__trend_state.init(self)  # it should be after initializing histories

        if self.__exe_mode in self.__fast_exe_modes:  # todo (2) IMP use it in online mode --> rethink it is necessary or not
            self.__init_incomplete_big_candles()
            self.__init_last_complete_big_candles()


    def stop_test(self):
        disconnect()

    def __calc_hist_init_start_time(self, candle_interval, days):
        return calc_last_tick_epoch(candle_interval, self.__curr_time) - int(
            days * 24 * 60 * 60 * 1000)

    def set_hist_1m_interval_days(self, days):
        self.__hist_1m_days = days

    @staticmethod
    def __wait_until_next_tick_1m():
        curr_time = utime.now_utc_epoch()
        if (curr_time % 60000) / 1000 > 5:
            time.sleep(1)  # todo why 1 sec??

    def __wait_for_init_curr_time(self):
        print("DP: waiting for first candle to initialize current time...")
        while self.__curr_time == 0:
            time.sleep(5)
        print("DP: curr_time is initialized on first candle.")

    def __update_db_with_requisite_histories(self):
        """
        Update to keep fill the candles db (no missing candles)
        """
        # For hist 1m may different number of days should be downloaded
        candle_interval = KLINE_INTERVAL_1MINUTE
        hist_start_time = self.__calc_hist_init_start_time(candle_interval, self.__config.hist_1m_days)
        print("Updating history " + candle_interval + " ...")
        self.__update_candles_db(candle_interval, hist_start_time)

        # For other histories same number of days should be downloaded
        for candle_interval in self.__candle_intervals:
            hist_start_time = self.__calc_hist_init_start_time(candle_interval, self.__config.big_hist_days)
            print("Updating history " + candle_interval + " ...")
            self.__update_candles_db(candle_interval, hist_start_time)

        need_to_sync = True
        candle_intervals = [KLINE_INTERVAL_1MINUTE] + self.__candle_intervals
        while need_to_sync:  # in case of new candles while downloading requisite histories
            need_to_sync = False
            for candle_interval in candle_intervals:
                last_close_time = self.__dbi.get_last_candle(candle_interval).close_time
                if last_close_time - self.__curr_time > candle_interval_in_millisecond(candle_interval):
                    need_to_sync = True
                    print(f"Need to synchronize db for hist_{candle_interval} !!!! ")
                    self.__update_candles_db(candle_interval, last_close_time)
        print(f"All requisite histories have been downloaded and updated in db.")

    def __update_candles_db(self, candle_interval, start_time, end_time=None):  # todo Test: should be tested
        # todo (2): think of renaming: it first download from source
        if end_time is None:
            end_time = calc_last_tick_epoch(candle_interval, self.__curr_time)
        # verify_size_of_required_history(candle_interval, start_time, end_time)
        histories = self.download_unsaved_histories(candle_interval, start_time, end_time)  # todo (2): rename:tike tike
        if len(histories) == 0:
            print("Database " + candle_interval + " is already up to date, no change is happened.")
        else:
            for history in histories:
                if len(history) > 0:
                    self.__save_candles_in_db(candle_interval, history)
                    self.__dbi.verify_db(candle_interval)
                else:
                    print("The given history " + candle_interval + " to be inserted in db is empty.")
                    self.__logger.warning("The given history " + candle_interval + " to be inserted in db is empty.")

            print("Database " + candle_interval + " is updated successfully.")

    def download_unsaved_histories(self, candle_interval, start_time, end_time=None):  # todo (2): more readable/rename
        """
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return:
        :rtype: list[list[Candle]]
        """
        # todo (1): validate start_time and end_time
        if self.__dbi.is_doc_empty(candle_interval):
            return [self.__get_candle_history(candle_interval, start_time, end_time)]
        else:  # todo (3): consider candle_interval as a measure to keep away from not necessary download request if db
            # actually is up to date
            oldest_open_time = self.__dbi.get_oldest_candle(candle_interval).open_time
            latest_close_time = self.__dbi.get_last_candle(candle_interval).close_time
            if end_time is not None:
                if start_time < oldest_open_time and latest_close_time < end_time:
                    history_left = self.__get_candle_history(candle_interval, start_time,
                                                             oldest_open_time - 1)  # to
                    # prevent getting oldest candle again
                    history_right = self.__get_candle_history(candle_interval, latest_close_time,
                                                              end_time)
                    return [history_left, history_right]
                elif start_time < oldest_open_time:
                    return [self.__get_candle_history(candle_interval, start_time, oldest_open_time - 1)]
                elif latest_close_time < end_time:
                    return [self.__get_candle_history(candle_interval, latest_close_time, end_time)]
            elif start_time < oldest_open_time:  # definitely latest_close_time < end_time where end_time is None
                history_left = self.__get_candle_history(candle_interval, start_time,
                                                         oldest_open_time - 1)  # to
                # prevent getting oldest candle again
                history_right = self.__get_candle_history(candle_interval, latest_close_time)
                return [history_left, history_right]
            else:  # definitely latest_close_time < end_time where end_time is None
                return [self.__get_candle_history(candle_interval, latest_close_time)]
        return []

    def __init_hist_1m_df(self):
        self.__hist_1m_df = common.hist_to_data_frame(self.__hist_1m)

    def __update_hist_1m_from_db(self):
        """
        It is initiated from db
        """
        # print(f"updating hist_1m (curr_time = {utime.epoch_to_utc_datetime(self.__curr_time)}) ...")
        start_index_from_end = self.__calc_required_hist_1m_size()  # todo (1): rename start_index_from_end/ todo(1): fix val
        hist = self.__dbi.get_hist(KLINE_INTERVAL_1MINUTE, start_index_from_end=start_index_from_end)
        self.__hist_1m = hist
        # print(f"Last item in __hist_1m: {self.__hist_1m[-1].open_time}")

    def __set_hist_1m_df_from_hist_1m(self):
        self.__hist_1m_df = common.hist_to_data_frame(self.__hist_1m)

    def __update_curr_time(self, new_candle_1m):
        self.__curr_time = new_candle_1m.close_time + 1

    def __on_new_candle_1m(self, new_candle_1m):
        # todo (1): what if operations take more than 1 minute? first need to see it happens or not(use assert)
        # print(f"New candle has been received by DP: {new_candle_1m.open_time}")
        self.__update_curr_time(new_candle_1m)

        self.__received_complete_candle = self.__received_complete_candle + 1

        if self.__ready is False:
            print(f" **** DM is not ready while receiving new candle: {new_candle_1m.open_time} -- Received Candle: {self.__received_complete_candle}")
            self.__logger.warning(f"DM is not ready while receiving new candle: {new_candle_1m.open_time} -- Received Candle: {self.__received_complete_candle}")
            return

        self.__tic_toc.tic()

        # curr_time_as_datetime = utime.epoch_to_utc_datetime(epoch=self.__curr_time,
        #                                                     datetime_format="%d-%m-%Y %H:%M:%S")
        #
        # print(f"CandleNum: {self.__received_complete_candle} ---- CurrTime:{curr_time_as_datetime}")

        toc_tmp1 = self.__tic_toc.toc()

        self.__update_db_on_new_candle_1m(new_candle_1m)  # all necessitate documents (tables)

        toc_tmp2 = self.__tic_toc.toc()

        self.__update_hist_1m_from_db()

        toc_tmp3 = self.__tic_toc.toc()

        self.__set_hist_1m_df_from_hist_1m()

        toc_tmp4 = self.__tic_toc.toc()

        self.__update_trend_state()

        toc_tmp5 = self.__tic_toc.toc()

        self.__update_hist_1m_queues()
        self.__update_hist_1m_df_queues()
        self.__update_trend_state_queues()

        if self.__tic_toc.toc() >= 55:
            print(f"Handling received candle took {self.__tic_toc.toc()} sec")
            print(f"toc_tmp1: {toc_tmp1} -- toc_tmp2: {toc_tmp2} -- toc_tmp3: {toc_tmp3} -- toc_tmp4: {toc_tmp4} -- toc_tmp5: {toc_tmp5}")
            self.__logger.warning(f"Handling received candle took {self.__tic_toc.toc()} sec \n toc_tmp1: {toc_tmp1} -- toc_tmp2: {toc_tmp2} -- toc_tmp3: {toc_tmp3} -- toc_tmp4: {toc_tmp4} -- toc_tmp5: {toc_tmp5}")

    def on_new_candle_1m_sim(self, new_candle_1m):  # todo (5): if is necessary, send signal for each updated part
        """
        :param Candle new_candle_1m:
        """
        self.__update_curr_time(new_candle_1m)
        # self.__tic_toc.tic()
        self.__received_complete_candle = self.__received_complete_candle + 1

        # todo (5): isn't more readable to check ticks here?

        self.__update_db_and_candles_on_new_candle_1m(new_candle_1m)

        # todo (2): in case of missing candles send [missing candles, new_candle]: (on purpose missing in simulation)
        self.__update_hist_1m_by_new_candles([new_candle_1m])
        self.__update_hist_1m_df_by_new_candles([new_candle_1m])  # to increase updating ema

        self.__update_trend_state()

        # note: histories, trend lines and trend state are considered as the information are updated by DP
        self.__update_hist_1m_queues()
        self.__update_hist_1m_df_queues()
        self.__update_trend_state_queues()
        # print(f"{self.__tic_toc.toc()}")

    def __update_db_and_candles_on_new_candle_1m(self, new_candle_1m):  # used only in test mode
        if self.__exe_mode in self.__fast_exe_modes:  # IMP: assuming there is no candle missing
            self.__update_incomplete_big_candles(new_candle_1m)
            for candle_interval, complete_big_candle in self.__remove_completed_big_candles():
                self.__last_complete_big_candles[candle_interval] = complete_big_candle
        else:
            self.__update_db_on_new_candle_1m(new_candle_1m)  # all necessitate documents (tables)

    def __update_hist_1m_by_new_candles(self, candles):
        """
        :param list[Candle] candles:
        """
        for candle in candles:
            self.__hist_1m.popleft()
            self.__hist_1m.append(candle)

    def __update_hist_1m_df_by_new_candles(self, candles):
        """
        :param list[Candle] candles:
        """
        for candle in candles:
            # set inplace=True to apply on this data frame, otherwise it returns a new df.
            self.__hist_1m_df.drop(0, inplace=True)
            # Can only append a dict if ignore_index=True, also, append in pd.DataFrame is not in place
            self.__hist_1m_df = self.__hist_1m_df.append(candle.to_dict(), ignore_index=True)

    def __update_trend_state(self):
        self.__trend_state.update(self.__curr_time, self.__hist_1m_df)

    def get_candle(self, candle_interval, open_time):
        """
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype Candle:
        """
        return self.__data_source.get_candle(candle_interval=candle_interval, open_time=open_time)

    def __get_candle_history(self, candle_interval, start_time, end_time=None):
        return self.__data_source.get_candle_history(candle_interval=candle_interval, start_time=start_time,
                                                     end_time=end_time)

    def __update_incomplete_big_candles(self, new_candle_1m):  # used only in test mode
        """
        :param Candle new_candle_1m:
        """
        # todo (2) IMP: get the set of candle intervals from config
        for candle_interval in self.__candle_intervals:
            incomplete_candle = self.__incomplete_big_candles[candle_interval]
            if incomplete_candle is None:
                self.__incomplete_big_candles[candle_interval] = create_candle_from_hist_1m(deque([new_candle_1m]),
                                                                                            candle_interval)
            else:
                update_incomplete_big_candle(incomplete_candle, new_candle_1m)

    def __remove_completed_big_candles(self):  # used only in test mode
        """
        :return:
        :rtype: list[(str, Candle)]
        """
        result = []
        for candle_interval in self.__candle_intervals:
            incomplete_candle = self.__incomplete_big_candles[candle_interval]
            if is_a_complete_candle(candle_interval, incomplete_candle):
                result.append((candle_interval, incomplete_candle))
                self.__incomplete_big_candles[candle_interval] = None
        return result

    # todo (4): to be more readable, it is better to separate actions regarding to missing situation:
    def __update_db_on_new_candle_1m(self, new_candle):
        if self.__is_any_missing_candle_on_new_candle_1m(new_candle):
            new_candles_1m = self.__download_missing_candles_1m()
            if len(new_candles_1m) == 0:
                raise Exception("Failed in downloading missing candles (even new candle is not returned)")
            print(f"{len(new_candles_1m)} missing candles are downloaded.")
            self.__logger.warning(f"{len(new_candles_1m)} missing candles are downloaded.")
            self.__save_candles_in_db(KLINE_INTERVAL_1MINUTE, new_candles_1m)

        else:
            new_candles_1m = [new_candle]
            self.__save_candles_in_db(KLINE_INTERVAL_1MINUTE, new_candles_1m)

        # self.__tic_toc.tic()
        self.__dbi.verify_db(KLINE_INTERVAL_1MINUTE)
        # print(self.__tic_toc.toc())
        # todo (2): flexible to config file
        # self.__tic_toc.tic()
        for candle_interval in self.__candle_intervals:
            unsaved_candles = self.__create_unsaved_big_candles(candle_interval)
            # print(self.__tic_toc.toc())
            # self.__tic_toc.tic()
            self.__save_candles_in_db(candle_interval, unsaved_candles)
            self.__dbi.verify_db(candle_interval)
        # print(self.__tic_toc.toc())

    def __is_any_missing_candle_on_new_candle_1m(self, new_candle):  # todo (2) rename
        last_candle_1m = self.__hist_1m[-1]
        if not are_candles_consecutive(KLINE_INTERVAL_1MINUTE, last_candle_1m, new_candle):
            missing_num = calc_diff_two_candles(KLINE_INTERVAL_1MINUTE, last_candle_1m, new_candle) - 1
            new_open_time = utime.epoch_to_utc_datetime(new_candle.open_time)
            last_open_time = utime.epoch_to_utc_datetime(last_candle_1m.open_time)
            new_close_time = utime.epoch_to_utc_datetime(new_candle.close_time)
            last_close_time = utime.epoch_to_utc_datetime(last_candle_1m.close_time)
            msg = f"Missing {missing_num} candles - New: {new_open_time}/{new_close_time} - " \
                  f"Last: {last_open_time}/{last_close_time}"
            print(msg)
            self.__logger.warning(f"{msg}")
            return True
        return False

    def __download_missing_candles_1m(self):
        last_saved_candles = self.__dbi.get_last_candle(KLINE_INTERVAL_1MINUTE)
        candles_1m = self.download_unsaved_histories(KLINE_INTERVAL_1MINUTE, last_saved_candles.close_time)
        return candles_1m

    def __create_unsaved_big_candles(self, candle_interval):  # todo (3): rename or description
        last_saved_close_time = self.__dbi.get_last_candle(candle_interval).close_time
        # __curr_time is required because of SRP in __create_big_candles_over_hist_1m
        return self.__create_big_candles_over_hist_1m(candle_interval, last_saved_close_time, self.__curr_time)

    def __create_big_candles_over_hist_1m(self, candle_interval, start, end):
        histories_1m = self.__get_histories_1m_between_ticks(candle_interval, start, end)
        candles = []
        for hist in histories_1m:  # no hist is empty according to __get_histories_between_ticks
            candles.append(create_candle_from_hist_1m(hist, candle_interval))
        return candles

    def __get_histories_1m_between_ticks(self, candle_interval, start, end):
        histories_1m = []  # hist per unsaved completed candle
        tick_times = get_tick_times_in_interval(candle_interval, start, end)
        for i in range(len(tick_times) - 1):
            # Note: get_hist should return hist_1m regardless to the candle_interval
            hist = self.__dbi.get_hist(KLINE_INTERVAL_1MINUTE, start_time=tick_times[i], end_time=tick_times[i + 1] - 1)
            # todo (1) check possibility and criticality
            if len(hist) == 0:
                warn_msg = f"Unexpected empty hist between ticks: {candle_interval}" \
                           f" - T1={utime.epoch_to_utc_datetime(tick_times[i])}" \
                           f" - T2={utime.epoch_to_utc_datetime(tick_times[i + 1])}"
                print(warn_msg)
                self.__logger.warning(warn_msg)
            else:  # only append to list if is not empty
                histories_1m.append(hist)
        return histories_1m

    def __save_candle_in_db(self, candle_interval, new_candle):
        self.__dbi.save_candle_in_db(candle_interval, new_candle)

    def __save_candles_in_db(self, candle_interval, candles):  # todo (1): get candle model here (or in db)
        for candle in candles:
            self.__dbi.save_candle_in_db(candle_interval, candle)

    # ----- Updating MP Queues -----
    def __update_hist_1m_queues(self):
        # if self.__exe_mode == EXE_FASTEST:
        #     for hist_1m_queue in self.__hist_1m_queues:
        #         hist_1m_queue.put([new_candle_1m])
        # else:
        for hist_1m_queue in self.__hist_1m_queues:
            hist_1m_queue.put(self.__hist_1m.copy())  # instead of list(self.__hist_1m)

    def __update_hist_1m_df_queues(self):
        for hist_1m_df_queue in self.__hist_1m_df_queues:  # See issue #412
            hist_1m_df_queue.put(self.__hist_1m_df.copy())  # deep copy
            # print(f"DP: put hist - {hist_1m_df_queue.qsize()}")

    def __update_trend_state_queues(self):
        for trend_state_queue in self.__trend_state_queues:
            trend_state_queue.put(self.__trend_state)
            # print(f"DP: put trend - {trend_state_queue.qsize()}")

    # ----- End of Updating MP Queues -----

    # ----- Initialization Methods -----

    def __init_incomplete_big_candles(self):  # used in test mode
        # todo (2) IMP: get the set of candle intervals from config
        for candle_interval in self.__candle_intervals:
            last_saved_candle = self.__dbi.get_last_candle(candle_interval)
            # todo (1) IMP: be sure that there is no need to use last_saved_candle.close_time + 1
            hist_1m = self.__dbi.get_hist(KLINE_INTERVAL_1MINUTE, start_time=last_saved_candle.close_time)
            incomplete_candle = create_candle_from_hist_1m(hist_1m, candle_interval)
            self.__incomplete_big_candles[candle_interval] = incomplete_candle

    def __init_last_complete_big_candles(self):  # used in test mode
        # todo (2)IMP: get the set of candle intervals from config
        for candle_interval in self.__candle_intervals:
            self.__last_complete_big_candles[candle_interval] = self.__incomplete_big_candles[candle_interval]

    # ----- End of Initialization Methods -----

    def __update_hits_1m(self, new_candle):
        """
        :param Candle new_candle:
        """
        self.__hist_1m.popleft()  # removing oldest candle
        self.__hist_1m.append(new_candle)
        print("Local hist_1m is updated by new candle")

    def __calc_required_hist_1m_size(self):
        """
        :return:
        :rtype:int
        """
        return self.__hist_1m_days * 24 * 60

    def get_last_candle(self,
                        candle_interval):  # todo(1): it cannot be used anytime if __last_complete_big_candles is not initialized
        if self.__exe_mode in self.__fast_exe_modes:
            # todo: (2) if it works well use it in all modes.
            return self.__last_complete_big_candles[candle_interval]  # it is a dictionary
        else:
            return self.__dbi.get_last_candle(candle_interval)

    def get_last_candles(self, intervals=None):
        if intervals is None:
            intervals = self.__candle_intervals
        last_candles = {}
        for candle_interval in intervals:
            last_candle = self.__dbi.get_last_candle(candle_interval)
            last_candles[candle_interval] = last_candle
        return last_candles

    def get_candle_intervals(self):
        """
        returns list of candle_interval set by designer in config
        :return: list[str]
        :rtype:
        """
        return self.__candle_intervals

    def get_hist_1m(self):
        """
        returns a reference to hist_1m
        :return:
        :rtype: deque[Candle]
        """
        return self.__hist_1m

    def get_hist_1m_df(self):
        """
        returns a reference to hist_1m_df
        :return:
        :rtype: pd.DataFrame
        """
        return self.__hist_1m_df

    def get_hist(self, candle_interval, start_time, end_time):
        return self.__dbi.get_hist(candle_interval, start_time=start_time, end_time=end_time)

    def get_trend_state(self):
        """
        returns a reference to trend_state
        :return:
        :rtype: TrendState
        """
        return self.__trend_state


# ----- Config Section ----

class DataProviderConfig:
    """
    :type symbol: str
    :type market_config: finance.binance.market.MarketConfig
    :type slines_dir: str or None
    :type hist_1m_days: int
    :type big_hist_days: int
    :type dp_log_file: str
    """

    def __init__(self, symbol, market_config, slines_dir,
                 hist_1m_days, candle_intervals, big_hist_days, dp_log_file, db_log_file):
        self.symbol = symbol
        self.market_config = market_config
        # self.trend_state_config = trend_state_config  # has been removed
        self.slines_dir = slines_dir
        self.hist_1m_days = hist_1m_days
        self.candle_intervals = candle_intervals
        self.big_hist_days = big_hist_days
        self.dp_log_file = dp_log_file
        self.db_log_file = db_log_file

# ----- End of Config Section ----
