from finance.analysis.indicators import atr
from finance.models.candles import Candle
from finance.tmp.extrema_tracker_3 import ExtremaTracker
from finance.utilities.uio import ulog
from finance.utilities.ufinance import common
from finance.utilities.utime import TicToc
from finance.analysis.trendstate.trend_state import TrendState
from finance.models.extremum import Extremum


class TrendStateDC(TrendState):
    # todo (3): complete docstring
    # NOTE:
    # DF in df_histories_atr doesn't has the same structure as DF created by downloaded history. It is created by converting history of candle objects to DF history
    """
    :type __config: TrendStateConfigDC
    :type __df_histories_atr: dict or None
    :type __histories_ext: dict or None
    :type __small_ext_tracker: ExtremaTracker or None
    :type __large_ext_tracker: ExtremaTracker or None
    """

    # todo(2) use same data structure of __histories_lbk for all hist_1m(df)
    # todo(2) check docstring of __histories_atr

    def __init__(self, config):
        """
        :param TrendStateConfigDC config:
        """

        super().__init__(config)
        self.__config = config
        self.__data_provider = None

        self.__candle_intervals = [config.small_interval, config.large_interval]  # required to check valid ticks todo (1): better name

        self.update_time = 0

        self.__last_candles = {}  # new, is needed by DecisionMaker
        self.__atr_data = {}
        self.__df_histories_atr = {}  # dictionary of df histories
        self.__histories_ext = {}  # IMP: are the same as __df_histories_atr but not as df, as deque[Candle] and only are used for initialization of ext_trackers. Never be updated
        self.__large_ext_tracker = None
        self.__small_ext_tracker = None

        self.__logger = ulog.get_default_logger(__name__, config.log_file)

        self.__tic_toc = TicToc()

        log_msg = f"Init: Small and large intervals: {self.__candle_intervals}"
        self.__logger.info(log_msg)

    def __getstate__(self):
        # Copy the object's state from self.__dict__ which contains
        # all our instance attributes. Always use the dict.copy()
        # method to avoid modifying the original state.
        state = self.__dict__.copy()
        # Remove the un-picklable entries.
        del state['_TrendStateDC__data_provider']
        del state['_TrendStateDC__df_histories_atr']
        del state['_TrendStateDC__histories_ext']
        return state

    def __setstate__(self, state):
        # Restore instance attributes (i.e., filename and lineno).
        self.__dict__.update(state)
        # Restore the previously opened file's state. To do so, we need to
        # reopen it and read from it until the line count is restored.
        self.__data_provider = None
        self.__df_histories_atr = None
        self.__histories_ext = None

    def init(self, data_provider):
        self.__data_provider = data_provider
        self.__init_last_candles(data_provider.get_last_candles())
        self.__init_histories()  # histories for atr and ext_trackers, note: atr needs df, trackers need list, also, trackers only need them for initialization
        self.__init_atr_data()  # should be after __init_histories_atr
        self.__init_ext_trackers()

    def update(self, curr_time, hist_1m_df):
        ticks = common.get_ticks(curr_time)
        required_ticks = [tick for tick in ticks if tick in self.__candle_intervals]  # todo (1) static
        if len(required_ticks) > 0:
            self.__on_new_ticks(required_ticks)

    def __on_new_ticks(self, ticks):
        log_msg = f"New ticks: {ticks}"
        self.__logger.info(log_msg)

        self.__update_last_candles(self.__data_provider.get_last_candles(ticks))
        self.__update_histories_atr(ticks)
        self.__update_atr_data(ticks)
        self.__update_ext_trackers(ticks)

    # Last candle section
    def __init_last_candles(self, last_candles):
        self.__last_candles = last_candles

        log_msg = f"Init: num of last candles: {len(last_candles)}"
        self.__logger.info(log_msg)

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

    # ATR Section:
    def __init_histories(self):
        for atr_config in self.__config.atr_configs:
            hist = self.__init_hist(atr_config)
            self.__histories_ext[atr_config.candle_interval] = hist

            log_msg = f"Init: len of init hist({atr_config.candle_interval}): {len(hist)}"
            self.__logger.info(log_msg)

            hist_df = common.hist_to_data_frame(hist)
            self.__df_histories_atr[atr_config.candle_interval] = hist_df

    def __init_hist(self, atr_config):  # for trending
        """
        It is initiated from db
        :param finance.analysis.indicators.atr.AtrConfig atr_config:
        :return
        :rtype deque[Candle]
        """
        print("Initializing hist for : " + atr_config.candle_interval)
        start_time = atr_config.start_time
        end_time = atr_config.end_time  # if end_time is None, history up to now is loaded.
        hist = self.__data_provider.get_hist(atr_config.candle_interval, start_time=start_time, end_time=end_time)
        return hist

    def __init_atr_data(self):
        for candle_interval in self.__candle_intervals:
            atr_ = atr.calc_atr(self.__df_histories_atr[candle_interval])
            self.__atr_data[candle_interval] = atr_

    def __update_histories_atr(self, ticks):
        for candle_interval in self.__df_histories_atr:
            if candle_interval in ticks:
                df_hist = self.__df_histories_atr[candle_interval]
                last_candle_in_hist = df_hist.iloc[-1]
                next_candle_open_time = last_candle_in_hist.close_time + 1  # Note, it is expected that the next candle (i.e. 15m, 1h, 4h) has already generated in data provider
                next_candle = self.__data_provider.get_candle(candle_interval, next_candle_open_time)

                # todo (1) or use get_last_candle, if is ok, do the same for __update_histories_lbk

                # set inplace=True to apply on this data frame, otherwise it returns a new df.
                self.__df_histories_atr[candle_interval].drop(0, inplace=True)
                # Can only append a dict if ignore_index=True, also, append in pd.DataFrame is not in place
                self.__df_histories_atr[candle_interval] = self.__df_histories_atr[candle_interval].append(
                    next_candle.to_dict(), ignore_index=True)

    def __update_atr_data(self, ticks):
        for candle_interval in self.__candle_intervals:
            if candle_interval in ticks:
                atr_ = atr.calc_atr(self.__df_histories_atr[candle_interval])
                self.__atr_data[candle_interval] = atr_

    def get_atr(self, candle_interval):
        return self.__atr_data[candle_interval]

    # Extremum Section:
    def __init_ext_trackers(self):
        small_interval = self.__config.small_interval
        large_interval = self.__config.large_interval

        self.__large_ext_tracker = ExtremaTracker(self.__histories_ext[large_interval], large_interval, 3, 1)
        self.__small_ext_tracker = ExtremaTracker(self.__histories_ext[small_interval], small_interval, 1, 1)

    def __update_ext_trackers(self, ticks):
        small_interval = self.__config.small_interval
        if small_interval in ticks:
            self.__small_ext_tracker.atr = self.__atr_data[small_interval]
            small_candle = self.__last_candles[small_interval]
            self.__small_ext_tracker.on_new_candle(small_candle)

        large_interval = self.__config.large_interval
        if large_interval in ticks:
            self.__large_ext_tracker.atr = self.__atr_data[large_interval]
            large_candle = self.__last_candles[large_interval]
            self.__large_ext_tracker.on_new_candle(large_candle)

    def get_last_small_min(self):
        """
        :return:
        :rtype: Extremum
        """
        return self.__small_ext_tracker.get_last_minimum()

    def get_last_small_max(self):
        """
        :return:
        :rtype: Extremum
        """
        return self.__small_ext_tracker.get_last_maximum()

    def is_new_large_extremum_useful(self):
        return self.__large_ext_tracker.is_new_extremum_useful()

    def get_last_large_extremum(self):
        """
        :return:
        :rtype: Extremum
        """
        return self.__large_ext_tracker.get_last_extremum()

    def get_last_large_candle(self):
        return self.__last_candles[self.__config.large_interval]

    def get_last_small_candle(self):
        return self.__last_candles[self.__config.small_interval]


class TrendStateConfigDC:
    """
    :type atr_configs: list[finance.analysis.indicators.atr.AtrConfig]
    :type small_interval: str
    :type large_interval: str
    :type log_file: str
    """

    # todo (1) handle in some configs are None
    def __init__(self, atr_configs, small_interval, large_interval, log_file):
        self.atr_configs = atr_configs
        self.small_interval = small_interval
        self.large_interval = large_interval
        self.log_file = log_file
