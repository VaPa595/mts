import math
import time
from collections import deque

import pandas as pd
from binance import ThreadedWebsocketManager, Client
from binance.enums import KLINE_INTERVAL_1MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR, KLINE_INTERVAL_15MINUTE
from mongoengine import disconnect, connect

from finance.analysis.trendlines.trend_lines import TrendLinesApi
from finance.analysis.trendstate.trend_state_brk import TrendState
from finance.utilities.ufinance import common
from finance.utilities.ufinance.common import candle_interval_in_millisecond, calc_last_tick_epoch, get_ticks, \
    calc_diff_two_candles, are_candles_consecutive, get_tick_times_in_interval, create_candle_from_hist_1m
from finance.models.candles import Candle
from finance.modules.enums import EXE_FAST
from finance.utilities import utime
from finance.utilities.uio import ulog
from finance.utilities.utime import TicToc



def is_a_complete_socket_candle(socket_candle_msg):
    return socket_candle_msg['k']['x']


def convert_socket_candle_to_simple_model(socket_msg, candle_interval):
    """
    :param dict socket_msg:
    :param str candle_interval:
    :return:
    :rtype: Candle
    """
    candle_model = common.get_candle_model(candle_interval)

    return candle_model(open=socket_msg['k']['o'], high=socket_msg['k']['h'], low=socket_msg['k']['l'],
                        close=socket_msg['k']['c'], volume=socket_msg['k']['v'], open_time=socket_msg['k']['t'],
                        close_time=socket_msg['k']['T'])


def convert_historical_candles_to_simple_model(full_history, candle_interval):
    """
    :param list[list[str]] full_history: full_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
    :param str candle_interval:
    :return:
    :rtype: list[Candle]
    """
    candle_model = common.get_candle_model(candle_interval)

    simple_candles = [candle_model(open=full_candle[1], high=full_candle[2], low=full_candle[3],
                                   close=full_candle[4], volume=full_candle[5], open_time=full_candle[0],
                                   close_time=full_candle[6]) for full_candle in full_history]
    return simple_candles


def convert_full_candle_to_simple_candle(full_candle, candle_interval):
    """
    :param list[str] full_candle: full_candle: [OpenTime, Open, High, Low, Close, Volume, CloseTime, ...]
    :param str candle_interval:
    :return:
    :rtype: Candle
    """
    candle_model = common.get_candle_model(candle_interval)

    simple_candle = candle_model(open=full_candle[1], high=full_candle[2], low=full_candle[3],
                                 close=full_candle[4], volume=full_candle[5], open_time=full_candle[0],
                                 close_time=full_candle[6])
    return simple_candle


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


def verify_candle_socket_msg(msg, candle_interval):
    """
    :param dict msg: Full candle received by websocket
    :param str candle_interval:
    """
    if msg['e'] == 'error':
        raise Exception("Socket " + candle_interval + " Error (probably is disconnected)")


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


class HistoricalCandleData:
    """
    :type name: str unique name
    :type candle_interval: str  interval of the candle: i.e. 1m, 15m, 1h, 4h
    :type hist: deque[Candle]
    """

    def __init__(self, name, candle_interval, hist):
        self.name = name
        self.candle_interval = candle_interval
        self.hist = hist
        self.__tic_toc = TicToc()

    def get_close_prices(self):
        result = [candle.close for candle in self.hist]  # todo (4): it imposes additional O(n) time overhead
        return result


class NewDataProvider:  # todo (4): separate public and private methods,  # todo (2): complete docstring
    """
    :type __config: DataProviderConfig
    :type __all_hist_for_trending: list[HistoricalCandleData] or None
    :type __hist_1m_queues: list[multiprocessing.Queue]
    :type __hist_1m_df_queues: list[multiprocessing.Queue]
    :type __trend_state_queues: list[multiprocessing.Queue]

    :type __hist_1m: deque[Candle] or None
    :type __hist_1m_df: pd.DataFrame or None
    :type __exe_mode: str
    :type __logger: logging.Logger
    """

    # todo (3) find a systematic way to keep active candle_intervals (some improvements are done)
    def __init__(self, config, source, all_data_frames_dic, hist_1m_queues, hist_1m_df_queues, trend_state_queues,
                 exe_mode):
        self.__curr_time = 0  # epoch time, it will be updated on each new candle1m, not used before first update
        # todo (2) rename __curr_time as current_time is used in a method
        self.__config = config
        self.__hist_1m = None  # under evaluation history for trading
        self.__hist_1m_df = None  # new: hist_1m as pandas.DataFrame to fast calculation of EMA (preventing hist to DF)

        # todo (2): think of converting to dictionary
        # todo (2): rename, all_hist_for_trend_state, I'm note sure 'trending' is good
        self.__all_hist_for_trending = None  # list of under evaluation histories for finding trend lines

        self.__hist_consumers = []
        self.__full_consumers = []

        self.__candle_socket = CandleSocket(self.__config.market_config.api_key, self.__config.market_config.api_secret)
        self.__hc_downloader = HistoricalCandlesDownloader(source, self.__config.symbol,
                                                           self.__config.market_config.api_key,
                                                           self.__config.market_config.api_secret, all_data_frames_dic)
        self.__dbm = DataBaseManager()

        # trending related variables
        self.__hlines_dir = self.__config.hlines_dir  # directory

        self.__hist_1m_days = self.__config.hist_1m_days
        self.__hlines_configs = self.__config.trend_state_config.slines_configs
        self.__breaking_configs = self.__config.trend_state_config.breaking_configs
        self.__trend_lines_finder = TrendLinesFinder()  # todo (2): static usage?
        self.__trend_state = TrendState(self.__config.trend_state_config)

        self.__received_complete_candle = 0

        self.__hist_1m_queues = hist_1m_queues
        self.__hist_1m_df_queues = hist_1m_df_queues
        self.__trend_state_queues = trend_state_queues

        self.__tic_toc = TicToc()
        self.__incomplete_big_candles = {}  # Only for db-less simulation, one key for each interval in {15m, 1h, 4h}
        self.__exe_mode = exe_mode
        self.__last_complete_big_candles = {}
        self.__logger = ulog.get_default_logger(__name__, self.__config.log_file)

        self.__logger.info("DP is initialized.")

    def start(self):
        self.__logger.info("starting...")
        connect('finance_db')
        self.__candle_socket.init()

        self.__wait_until_next_tick_1m()
        # todo (2): check _curr_time initialization again:
        self.__curr_time = utime.now_utc_epoch()  # it is better to be close to __update_candles_db_according_to_configs
        self.__update_candles_db_according_to_configs()  # it is necessary before initializing histories.
        self.synchronize_db()

        self.__tic_toc.tic()  # **

        self.__update_hist_1m_from_db()  # at this point it is initializing
        self.__init_hist_1m_df()  # should be called after initializing hist_1m
        self.__init_all_histories_for_trending_from_db()
        self.__initializing_trend_lines()  # should be after initializing histories for trending
        self.__init_trend_state()

        self.__logger.info("all prerequisite jobs are done.")

        # should be last:
        self.__logger.info("starting candle socket ...")
        self.__candle_socket.start_individual_stream(callback=self.__on_new_candle_1m, symbol=self.__config.symbol,
                                                     candle_interval=KLINE_INTERVAL_1MINUTE)
        self.__logger.info("candle socket is started.")

        if self.__tic_toc.toc() >= 55:  # **
            print(f"Initialization took {self.__tic_toc.toc()} sec")
            self.__logger.warning(f"Initialization took {self.__tic_toc.toc()} sec")

    def stop(self):
        disconnect()  # todo (4): use db prefix
        self.__candle_socket.stop()
        self.__logger.info("Disconnecting from db and candle socket.")

    def start_test(self, test_name, curr_time):
        connect(test_name)

        self.__curr_time = curr_time  # it is better to be close to __update_candles_db_according_to_configs
        self.__update_candles_db_according_to_configs()  # it is necessary before initializing histories.

        self.__update_hist_1m_from_db()
        self.__init_hist_1m_df()  # should be called after initializing hist_1m
        self.__init_all_histories_for_trending_from_db()
        self.__initializing_trend_lines()  # should be after initializing histories for trending

        self.__init_trend_state()

        if self.__exe_mode == EXE_FAST:  # todo (3) IMP use it in online mode --> rethink it is necessary or not
            self.__init_incomplete_big_candles()
            self.__init_last_complete_big_candles()

    def stop_test(self):
        disconnect()

    def __calc_hist_1m_init_start_time(self):  # todo (2) rename  # todo (2): mention is related to curr_time
        return calc_last_tick_epoch(KLINE_INTERVAL_1MINUTE, self.__curr_time) - int(
            self.__hist_1m_days * 24 * 60 * 60 * 1000)

    def set_hist_1m_interval_days(self, days):
        self.__hist_1m_days = days

    def add_hist_consumer(self, hist_consumer):  # todo (4): is it useful?
        self.__hist_consumers.append(hist_consumer)

    def add_full_consumer(self, full_consumer):  # todo (4): is it useful?
        self.__full_consumers.append(full_consumer)

    @staticmethod
    def __wait_until_next_tick_1m():
        curr_time = utime.now_utc_epoch()
        if (curr_time % 60000) / 1000 > 5:
            time.sleep(1)

    def __update_candles_db_according_to_configs(self):
        """
        Update to keep fill the candles db (no missing candles)
        """
        print("Updating essential history 1m ...")
        start_time_1m = self.__calc_hist_1m_init_start_time()
        self.__update_candles_db(KLINE_INTERVAL_1MINUTE, start_time_1m)

        updated_histories = []  # For each candle_interval only one document(table) exists (regardless of config# name)
        for hline_config in self.__hlines_configs:
            if hline_config.candle_interval not in updated_histories:
                print("Updating essentials history " + hline_config.candle_interval + " ...")
                # todo (2): should be notified somewhere that we don't use hline_config.end_time
                self.__update_candles_db(hline_config.candle_interval, hline_config.start_time)
                updated_histories.append(hline_config.candle_interval)

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
                    self.__dbm.verify_db(candle_interval)
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
        if self.__dbm.is_doc_empty(candle_interval):
            return [self.__hc_downloader.get_light_history(candle_interval, start_time, end_time)]
        else:  # todo (3): consider candle_interval as a measure to keep away from not necessary download request if db
            # actually is up to date
            oldest_open_time = self.__dbm.get_oldest_candle(candle_interval).open_time
            latest_close_time = self.__dbm.get_last_candle(candle_interval).close_time
            if end_time is not None:
                if start_time < oldest_open_time and latest_close_time < end_time:
                    history_left = self.__hc_downloader.get_light_history(candle_interval, start_time,
                                                                          oldest_open_time - 1)  # to
                    # prevent getting oldest candle again
                    history_right = self.__hc_downloader.get_light_history(candle_interval, latest_close_time, end_time)
                    return [history_left, history_right]
                elif start_time < oldest_open_time:
                    return [self.__hc_downloader.get_light_history(candle_interval, start_time, oldest_open_time - 1)]
                elif latest_close_time < end_time:
                    return [self.__hc_downloader.get_light_history(candle_interval, latest_close_time, end_time)]
            elif start_time < oldest_open_time:  # definitely latest_close_time < end_time where end_time is None
                history_left = self.__hc_downloader.get_light_history(candle_interval, start_time,
                                                                      oldest_open_time - 1)  # to
                # prevent getting oldest candle again
                history_right = self.__hc_downloader.get_light_history(candle_interval, latest_close_time)
                return [history_left, history_right]
            else:  # definitely latest_close_time < end_time where end_time is None
                return [self.__hc_downloader.get_light_history(candle_interval, latest_close_time)]
        return []

    def synchronize_db(self):  # todo (3): a better approach
        # todo (2): make sure there is no need to synchronize other histories (otherwise: rename to ..1m..)
        print("Synchronizing db hist_1m ...")
        self.__logger.info("Synchronizing db hist_1m ...")
        while 1:  # todo (2): use meaningful condition
            current_time = utime.now_utc_epoch()
            last_close_time_1m = self.__dbm.get_last_candle(KLINE_INTERVAL_1MINUTE).close_time
            if last_close_time_1m - current_time > candle_interval_in_millisecond(KLINE_INTERVAL_1MINUTE):
                print("!!!! Need to synchronize db hist_1m")
                self.__update_candles_db(KLINE_INTERVAL_1MINUTE, last_close_time_1m)
            else:
                break

    def __update_hist_1m_from_db(self):
        """
        It is initiated from db
        """
        # print(f"updating hist_1m (curr_time = {utime.epoch_to_utc_datetime(self.__curr_time)}) ...")
        start_index_from_end = self.__calc_required_hist_1m_size()  # todo (1): rename start_index_from_end/todo fix val
        hist = self.__dbm.get_hist(KLINE_INTERVAL_1MINUTE, start_index_from_end=start_index_from_end)
        self.__hist_1m = hist

    def __set_hist_1m_df_from_hist_1m(self):
        self.__hist_1m_df = common.hist_to_data_frame(self.__hist_1m)

    def __update_db_and_candles_on_new_candle_1m(self, new_candle_1m):  # used only in test mode
        if self.__exe_mode == EXE_FAST:  # IMP: assuming there is no candle missing
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

    def __init_hist_1m_df(self):
        self.__hist_1m_df = common.hist_to_data_frame(self.__hist_1m)

    def __update_hist_1m_df_by_new_candles(self, candles):
        """
        :param list[Candle] candles:
        """
        for candle in candles:
            # set inplace=True to apply on this data frame, otherwise it returns a new df.
            self.__hist_1m_df.drop(0, inplace=True)
            # Can only append a dict if ignore_index=True, also, append in pd.DataFrame is not in place
            self.__hist_1m_df = self.__hist_1m_df.append(candle.to_dict(), ignore_index=True)

    def __update_trend_state_and_related_info(self):
        self.__trend_state.update_ema_data(self.__hist_1m_df)
        # self.__inform_hist_consumers(KLINE_INTERVAL_1MINUTE)  # IMPORTANT: it should be after updating trend lines
        ticks = get_ticks(self.__curr_time)
        if len(ticks) > 0:
            self.__update_histories_for_trending()
            self.__update_and_save_trend_lines()

            breaking_info_list_on_tick = self.__create_breaking_info_list_on_tick(ticks)
            for tick in ticks:
                if self.__exe_mode == EXE_FAST:
                    last_candle = self.__last_complete_big_candles[tick]  # it is a dictionary
                else:
                    last_candle = self.__dbm.get_last_candle(tick)
                self.__trend_state.set_last_candle(candle_interval=tick, last_candle=last_candle)
            self.__trend_state.on_new_ticks(breaking_info_list_on_tick)

    def __update_histories_for_trending(self):
        ticks = get_ticks(self.__curr_time)
        for hcd in self.__all_hist_for_trending:
            if hcd.candle_interval in ticks:
                last_candle_in_hist = hcd.hist[-1]
                next_candle_open_time = last_candle_in_hist.close_time + 1
                next_candle = self.__get_candle_by_open_time(hcd.candle_interval, next_candle_open_time)
                hcd.hist.popleft()  # removing oldest candle
                hcd.hist.append(next_candle)

    def __get_candle_by_open_time(self, candle_interval, open_time):
        """
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype Candle:
        """
        if self.__exe_mode == EXE_FAST:
            # it uses hc_downloader.all_data_frames_dic
            return self.__hc_downloader.get_candle_by_open_time(candle_interval, open_time)
        else:
            return self.__dbm.get_candle_by_open_time(candle_interval, open_time)

    def __on_new_candle_1m(self, msg):
        # todo (1): what if operations take more than 1 minute? first need to see it happens or not(use assert)
        self.__tic_toc.tic()
        verify_candle_socket_msg(msg, KLINE_INTERVAL_1MINUTE)
        if is_a_complete_socket_candle(msg):
            self.__received_complete_candle = self.__received_complete_candle + 1

            new_candle_1m = convert_socket_candle_to_simple_model(msg, KLINE_INTERVAL_1MINUTE)
            self.__curr_time = new_candle_1m.close_time + 1  # todo (3): define a method

            # curr_time_as_datetime = utime.epoch_to_utc_datetime(epoch=self.__curr_time,
            #                                                     datetime_format="%d-%m-%Y %H:%M:%S")
            #
            # print(f"CandleNum: {self.__received_complete_candle} ---- CurrTime:{curr_time_as_datetime}")

            self.__update_db_on_new_candle_1m(new_candle_1m)  # all necessitate documents (tables)

            self.__update_hist_1m_from_db()
            self.__set_hist_1m_df_from_hist_1m()

            self.__update_trend_state_and_related_info()

            # self.__inform_hist_consumers(KLINE_INTERVAL_1MINUTE)  # IMPORTANT: it should be after updating trend lines

            # self.__inform_full_consumers(KLINE_INTERVAL_1MINUTE)  # should be called after updating trend_state

            self.__update_hist_1m_queues()
            self.__update_hist_1m_df_queues()
            self.__update_trend_state_queues()
            if self.__tic_toc.toc() >= 55:
                print(f"Initialization took {self.__tic_toc.toc()} sec")
                self.__logger.warning(f"Initialization took {self.__tic_toc.toc()} sec")

    def on_new_candle_1m_sim(self, new_candle_1m):  # todo (5): if is necessary, send signal for each updated part
        """
        :param Candle new_candle_1m:
        """
        self.__tic_toc.tic()

        self.__received_complete_candle = self.__received_complete_candle + 1

        # it is ok, because time granularity is minute and all other processes are updated only after this
        self.__curr_time = new_candle_1m.close_time + 1
        # todo (5): isn't more readable to check ticks hear?

        self.__update_db_and_candles_on_new_candle_1m(new_candle_1m)

        # todo (2): in case of missing candles send [missing candles, new_candle]: (on purpose missing in simulation)
        self.__update_hist_1m_by_new_candles([new_candle_1m])
        self.__update_hist_1m_df_by_new_candles([new_candle_1m])  # to increase updating ema

        self.__update_trend_state_and_related_info()

        # self.__inform_full_consumers(KLINE_INTERVAL_1MINUTE)  # should be called after updating trend_state

        # note: histories, trend lines and trend state are considered as the information are updated by DP
        self.__update_hist_1m_queues()
        self.__update_hist_1m_df_queues()
        self.__update_trend_state_queues()

        print(self.__tic_toc.toc())

    def __update_incomplete_big_candles(self, new_candle_1m):  # used only in test mode
        """
        :param Candle new_candle_1m:
        """
        # todo (2) IMP: get the set of candle intervals from config
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:
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
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:
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
        self.__dbm.verify_db(KLINE_INTERVAL_1MINUTE)
        # print(self.__tic_toc.toc())
        # todo (2): flexible to config file
        # self.__tic_toc.tic()
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:
            unsaved_candles = self.__create_unsaved_big_candles(candle_interval)
            # print(self.__tic_toc.toc())
            # self.__tic_toc.tic()
            self.__save_candles_in_db(candle_interval, unsaved_candles)
            self.__dbm.verify_db(candle_interval)
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
        last_saved_candles = self.__dbm.get_last_candle(KLINE_INTERVAL_1MINUTE)
        candles_1m = self.download_unsaved_histories(KLINE_INTERVAL_1MINUTE, last_saved_candles.close_time)
        return candles_1m

    def __create_unsaved_big_candles(self, candle_interval):  # todo (3): rename or description
        last_saved_close_time = self.__dbm.get_last_candle(candle_interval).close_time
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
            hist = self.__dbm.get_hist(KLINE_INTERVAL_1MINUTE, start_time=tick_times[i], end_time=tick_times[i + 1] - 1)
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
        self.__dbm.save_candle_in_db(candle_interval, new_candle)

    def __save_candles_in_db(self, candle_interval, candles):  # todo (1): get candle model here (or in db)
        for candle in candles:
            self.__dbm.save_candle_in_db(candle_interval, candle)

    def __update_and_save_trend_lines(self):  # (for matlab)
        ticks = get_ticks(self.__curr_time)
        for hcd in self.__all_hist_for_trending:
            if hcd.candle_interval in ticks:
                hline_config = self.__get_hline_config(hcd.name)
                hlines_info = self.__trend_lines_finder.update_hlines_info(hline_config, hcd.get_close_prices())
                self.__save_hlines_info(hlines_info)
                # print("hlines created and saved: " + hcd.name + f"-------- Start: "
                #                                                 f"{utime.epoch_to_utc_datetime(hcd.hist[0].open_time)}"
                #                                                 f"-----End: "
                #                                                 f"{utime.epoch_to_utc_datetime(hcd.hist[-1].open_time)}"
                #       )

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

    def __initializing_trend_lines(self):  # IMP: should be call after initializing __all_hist_for_trending
        for hcd in self.__all_hist_for_trending:
            hline_config = self.__get_hline_config(hcd.name)
            hlines_info = self.__trend_lines_finder.update_hlines_info(hline_config, hcd.get_close_prices())
            self.__save_hlines_info(hlines_info)
            # print("hlines created and saved: " + hcd.name)
            self.__logger.debug("Initial hlines are created and saved: " + hcd.name)

    def __init_trend_state(self):
        self.__trend_state.init_ema_data(self.__hist_1m_df)  # it should be before breaking_info

        breaking_info_list_on_last_tick = []  # todo (1): check again
        for breaking_config in self.__breaking_configs:
            candle = self.__dbm.get_last_candle(breaking_config.candle_interval)
            hlines_info = self.__trend_lines_finder.get_last_hlines_info(breaking_config.sline_name)
            hlines = hlines_info.hlines
            ema = self.__trend_state.get_ema(breaking_config.ema_name)
            breaking_info_list_on_last_tick.append(BreakingInfoOnTick(breaking_name=breaking_config.name,
                                                                      hline_name=breaking_config.sline_name,
                                                                      candle_interval=breaking_config.candle_interval,
                                                                      candle=candle, ema_dir=ema.dir, hlines=hlines))

        self.__trend_state.init_all_lines_breaking_status(self.__hist_1m, self.__hist_1m_df,
                                                          breaking_info_list_on_last_tick)

        last_candles = {}
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:  # todo (2):config
            last_candle = self.__dbm.get_last_candle(candle_interval)
            last_candles[candle_interval] = last_candle
        self.__trend_state.init_last_candles(last_candles)

    def __init_incomplete_big_candles(self):  # used in test mode
        # todo (2) IMP: get the set of candle intervals from config
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:
            last_saved_candle = self.__dbm.get_last_candle(candle_interval)
            # todo (1) IMP: be sure that there is no need to use last_saved_candle.close_time + 1
            hist_1m = self.__dbm.get_hist(KLINE_INTERVAL_1MINUTE, start_time=last_saved_candle.close_time)
            incomplete_candle = create_candle_from_hist_1m(hist_1m, candle_interval)
            self.__incomplete_big_candles[candle_interval] = incomplete_candle

    def __init_last_complete_big_candles(self):  # used in test mode
        # todo (2)IMP: get the set of candle intervals from config
        for candle_interval in [KLINE_INTERVAL_15MINUTE, KLINE_INTERVAL_1HOUR, KLINE_INTERVAL_4HOUR]:
            self.__last_complete_big_candles[candle_interval] = self.__incomplete_big_candles[candle_interval]

    def __init_all_histories_for_trending_from_db(self):
        self.__all_hist_for_trending = []
        for hline_config in self.__hlines_configs:
            hcd = self.__init_hist_for_trending_from_db(hline_config)
            self.__all_hist_for_trending.append(hcd)

    def __init_hist_for_trending_from_db(self, hline_config):
        """
        It is initiated from db
        :param HLineConfig hline_config:
        :return
        :rtype HistoricalCandleData
        """
        print("Initializing hist for hlines: " + hline_config.name)
        start_time = hline_config.start_time
        end_time = hline_config.end_time  # if end_time is None, history up to now is loaded.
        hist = self.__dbm.get_hist(hline_config.candle_interval, start_time=start_time, end_time=end_time)
        hcd = HistoricalCandleData(hline_config.name, hline_config.candle_interval, hist)
        return hcd

    # ----- End of Initialization Methods -----

    def __save_hlines_info(self, hlines_info):
        # file_abs_path = os.path.join(self.__hlines_dir, hlines_info.hist_name + ".json")
        # ujson.write_obj_to_json_file(hlines_info, file_abs_path)
        pass

    def __inform_hist_consumers(self, candle_interval):
        if candle_interval == KLINE_INTERVAL_1MINUTE:
            for hist_consumer in self.__hist_consumers:
                hist_consumer.on_new_hist(candle_interval, self.__hist_1m)
        else:
            raise Exception("Unexpected candle interval")

    def __inform_full_consumers(self, candle_interval):  # todo (6): rethink on candle_interval and hist_list
        histories_on_tick = {candle_interval: self.__hist_1m}  # you can add other histories as needed
        for full_consumer in self.__full_consumers:
            full_consumer.on_new_tick(candle_interval, histories_on_tick, self.__trend_state)

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

    def __get_hline_config(self, name):  # todo (5): think of creating a class which handles defined list
        """
        :param str name:
        :return:
        :rtype: HLineConfig
        """
        for hline_config in self.__hlines_configs:
            if hline_config.name == name:
                return hline_config
        raise Exception("Invalid hline_config")

    def __create_breaking_info_list_on_tick(self, ticks):
        breaking_info_list_on_tick = []
        for breaking_config in self.__breaking_configs:
            if breaking_config.candle_interval in ticks:
                candle = self.get_last_candle(breaking_config.candle_interval)
                hlines_info = self.__trend_lines_finder.get_last_hlines_info(breaking_config.sline_name)
                hlines = hlines_info.hlines
                ema = self.__trend_state.get_ema(breaking_config.ema_name)
                breaking_info_list_on_tick.append(BreakingInfoOnTick(breaking_name=breaking_config.name,
                                                                     hline_name=breaking_config.sline_name,
                                                                     candle_interval=breaking_config.candle_interval,
                                                                     candle=candle, ema_dir=ema.dir, hlines=hlines))
        return breaking_info_list_on_tick

    def get_last_candle(self, candle_interval):
        if self.__exe_mode == EXE_FAST:
            return self.__last_complete_big_candles[candle_interval]  # it is a dictionary
        else:
            return self.__dbm.get_last_candle(candle_interval)

    def get_hist_1m(self):
        """
        returns a reference to hist_1m
        :return:
        :rtype: deque[Candle]
        """
        return self.__hist_1m

    def get_trend_state(self):
        """
        returns a reference to trend_state
        :return:
        :rtype: TrendState
        """
        return self.__trend_state


class CandleSocket:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret)

    def init(self):
        self.twm.start()

    def start_individual_stream(self, callback, symbol, candle_interval):
        # self.twm.start_kline_socket(callback=self.handle_socket_message, symbol=self.symbol,
        #                             interval=KLINE_INTERVAL_1MINUTE, )

        self.twm.start_kline_futures_socket(callback=callback, symbol=symbol, interval=candle_interval)

    def stop(self):
        self.twm.stop()  # all stream will be stopped


class HistoricalCandlesDownloader:
    # todo (3): do something like (source, params) --> then init instance variables accordingly.
    # for offline source, consider separate excel file for each candle_interval (some may be None, except 1m), although
    # it is not needed right now.
    def __init__(self, source, symbol, api_key, api_secret, all_data_frames_dic):
        self.symbol = symbol
        self.__source = source
        if source == "Binance":  # todo (3): enum
            self.__api_key = api_key
            self.__api_secret = api_secret
        elif source == "DataFrame":
            self.__all_data_frames_dic = all_data_frames_dic

    def download(self, candle_interval, start_time, end_time=None):
        # todo (1): IMP, return types
        if self.__source == "Binance":
            return self.__download_from_binance(candle_interval, start_time, end_time)
        if self.__source == "DataFrame":
            return self.__read_from_data_frame(candle_interval, start_time, end_time)

    def get_light_history(self, candle_interval, start_time, end_time=None):
        # todo (2): IMP, SRP: converting to simple candle is not its job --> do as done in get_candle_by_open_time
        """
        Downloading historical candles of candle_interval in [start_time end_time] and converting to simple Candle
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        :return
        :rtype list[Candle]
        """
        full_history = self.download(candle_interval, start_time, end_time)
        # full_candle: OpenTime, Open, High, Low, Close, Volume, CloseTime, ...
        simple_candles = convert_historical_candles_to_simple_model(full_history, candle_interval)
        return simple_candles

    def __download_from_binance(self, candle_interval, start_time, end_time=None):
        """
        Downloading historical candles of candle_interval in [start_time end_time] from Binance
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        """
        print("start downloading history " + candle_interval + " ...")
        client = Client(self.__api_key, self.__api_secret)
        history = client.futures_historical_klines(symbol=self.symbol,
                                                   interval=candle_interval, start_str=start_time,
                                                   end_str=end_time)
        print("history " + candle_interval + " downloaded.")
        # todo (1) if end_time = none?
        # if not verify_history(history, candle_interval, start_time, end_time):
        #     raise Exception("Invalid downloaded history.")
        return history

    def __read_from_data_frame(self, candle_interval, start_time, end_time=None):
        # todo (4): IMP: flexible regarding to change in config??
        """
        Reading historical candles of candle_interval in [start_time end_time] from data frame
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_time: start time of the history in UTC epoch
        :param int end_time: end time of the history in UTC epoch
        """
        if start_time is not None and end_time is not None:
            hist_as_df = self.__all_data_frames_dic[candle_interval].loc[start_time:end_time]
            hist_as_np = hist_as_df.to_numpy()
            return hist_as_np
        if start_time is not None:
            hist_as_df = self.__all_data_frames_dic[candle_interval].loc[start_time:]
            hist_as_np = hist_as_df.to_numpy()
            return hist_as_np
        raise Exception(f"Invalid interval for downloading history: start_time={start_time}, end_time={end_time}")

    def get_candle_by_open_time(self, candle_interval, open_time):
        """
        Only for offline mode, retrieving from __all_data_frames_dic
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype Candle:
        """
        full_candle = self.__all_data_frames_dic[candle_interval].loc[open_time]
        simple_candle = convert_full_candle_to_simple_candle(full_candle, candle_interval)
        return simple_candle


class DataBaseManager:
    __logger = ulog.get_default_logger(__name__, "DP.log")  # todo (2): get from config

    @classmethod
    def save_history_in_db(cls, candle_interval, history):  # todo (4): just for log it should be class method
        """
        Saving a list of candles in the collection corresponding to the specified candle_interval
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param list[Candle] history: list of candles
        """
        if len(history) > 0:
            candle_model = common.get_candle_model(candle_interval)
            candle_model.objects.insert(history)
        else:
            print("The given history " + candle_interval + " to be inserted in db is empty.")
            cls.__logger.warning("The given history " + candle_interval + " to be inserted in db is empty.")

    @staticmethod
    def save_candle_in_db(candle_interval, candle):
        """
        Saving one candle in the collection corresponding to the specified candle_interval
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param Candle candle: given candle
        """
        candle_model = common.get_candle_model(candle_interval)
        try:
            candle_model.objects.insert(candle)
        except Exception as e:
            print(e)

    @staticmethod
    def is_doc_empty(candle_interval):
        """
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :return: Whether the collection is empty or not
        :rtype: Boolean
        """
        candle_model = common.get_candle_model(candle_interval)
        return candle_model.objects.first() is None

    @staticmethod
    def get_oldest_candle(candle_interval):
        """
        Oldest candle is the one with oldest open time
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :return: Oldest candle in the document
        :rtype: Candle
        """
        candle_model = common.get_candle_model(candle_interval)
        return candle_model.objects.order_by('open_time').first()

    @staticmethod
    def get_last_candle(candle_interval):
        """
        Earliest candle is the one with earliest open time
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :return: Earliest candle in the document
        :rtype: Candle
        """
        candle_model = common.get_candle_model(candle_interval)
        return candle_model.objects.order_by('-open_time').first()

    @staticmethod
    def verify_db(candle_interval):
        candle_model = common.get_candle_model(candle_interval)
        pipeline = [
            {"$group": {"_id": "$open_time", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None}, "count": {"$gt": 1}}},
            {"$project": {"open_time": "$_id", "_id": 0}}
        ]
        result = candle_model.objects.aggregate(pipeline)
        assert len(list(result)) == 0

    @staticmethod
    def get_hist(candle_interval, start_index=None, end_index=None, start_time=None, end_time=None,
                 start_index_from_end=None):  # todo (3): raise exception if all arguments have values
        """
        Define what will happen:
            if last_candles_num is not None the others are ignored
        :param str candle_interval: interval of the candle: i.e. 1m, 15m, 1h, 4h
        :param int start_index: start index of required interval
        :param int end_index: end index of required interval
        :param int start_time: start of the time interval including the history  # todo (3): better explain
        :param int end_time: end of the time interval including the history
        :param int start_index_from_end:
        :return:
        :rtype: deque[Candle]
        """
        if start_index is None and start_time is None and start_index_from_end is None:
            raise Exception("Start of an interval should be determined to get history.")
        candle_model = common.get_candle_model(candle_interval)
        if start_index_from_end is not None:
            queryset = candle_model.objects.order_by('-open_time')  # todo (1): try catch -- or raise exception
            if len(queryset) < start_index_from_end:
                print("Warning: the required history is more than the stored in db")
            # todo (1): check this is what should be: (validate the name: start_index_from_end)(validate '-open_time')
            deQ = deque(queryset[:start_index_from_end])  # note [: 5] returns indexes 0, 1, 2, 3, 4
            deQ.reverse()  # todo (1) check again why -open_time, and why reversing?
            return deQ
        if start_index is not None:
            queryset = candle_model.objects.order_by('open_time')  # todo (1): try catch
            deQ = deque(queryset[start_index:])  # note [: 5] returns indexes 0, 1, 2, 3, 4 # todo (1) validate
            return deQ
        # todo (1) handle [start_time end_time]
        # todo (1) if end_time is None
        if start_time is not None and end_time is not None:
            queryset = candle_model.objects(open_time__gte=start_time, close_time__lte=end_time)  # todo (1) try catch
            deQ = deque(queryset)  # todo validate using open_time for end_time is OK (make it rule if is OK) --> not ok
            # , it returns the candle that has open_time equal to 'end_time', too.
            return deQ
        if start_time is not None and end_time is None:
            queryset = candle_model.objects(open_time__gte=start_time)  # todo (1) try catch
            deQ = deque(queryset)
            return deQ

    @staticmethod
    def get_candle_by_open_time(candle_interval, open_time):
        """
        :param str candle_interval:
        :param int open_time:
        :return:
        :rtype: Candle
        """
        candle_model = common.get_candle_model(candle_interval)
        return candle_model.objects(open_time=open_time)[0]


class HlineInfo:  # todo (5) hline or sline (static/dynamic line is correct naming?)
    def __init__(self, hist_name, hlines, start, end):
        """
        :param str hist_name:
        :param list[float] hlines:
        :param int start:
        :param int end:
        """
        self.hist_name = hist_name
        self.hlines = hlines
        self.start = start
        self.end = end


class TrendLinesFinder:  # todo (2): in trend_state?
    # method in case of multi trading
    __all_last_hlines_info = {}

    @classmethod
    def update_hlines_info(cls, hline_config, points):
        if len(points) == 0:
            print(f"Empty points for getting trend lines: {hline_config.name}")  # todo, need to log?
        hlines = TrendLinesApi.get_slines(points, hline_config.static_tolerance, hline_config.static_density)
        hlines_info = HlineInfo(hline_config.name, hlines, -1, -1)  # todo (1) set start/end of history
        cls.__all_last_hlines_info[hline_config.name] = hlines_info
        return hlines_info

    @classmethod
    def get_all_last_hlines_info(cls):
        return cls.__all_last_hlines_info

    @classmethod
    def get_last_hlines_info(cls, name):
        """
        :param str name:
        :return:
        :rtype: HlineInfo
        """
        return cls.__all_last_hlines_info[name]  # todo (3) define type of the value in the dictionary


class BreakingInfoOnTick:  # todo (2): in trend_state?
    def __init__(self, breaking_name, hline_name, candle_interval, candle, ema_dir, hlines):
        self.breaking_name = breaking_name
        self.hline_name = hline_name
        self.candle_interval = candle_interval
        self.candle = candle
        self.ema_dir = ema_dir  # in future it is possible to need different ema for each config
        self.hlines = hlines


# ----- Config Section ----

class DataProviderConfig:
    """
    :type symbol: str
    :type market_config: finance.binance.market.MarketConfig
    :type trend_state_config: finance.analysis.trend_state.TrendStateConfig
    :type hlines_dir: str
    :type hist_1m_days: int
    :type log_file: str
    """
    def __init__(self, symbol, market_config, trend_state_config, hlines_dir,
                 hist_1m_days, log_file):
        self.symbol = symbol
        self.market_config = market_config
        self.trend_state_config = trend_state_config
        self.hlines_dir = hlines_dir
        self.hist_1m_days = hist_1m_days
        self.log_file = log_file

# ----- End of Config Section ----
