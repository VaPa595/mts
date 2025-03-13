from finance.analysis.trendlines import trend_lines as tl

####################################################################
from finance.utilities import utime


def verify_ranges(min_r, max_r, kind):
    if min_r < 0:
        raise Exception("Start day (" + kind + ") is out of range. Choose smaller.")
    if max_r < 0:
        raise Exception("End day (" + kind + ") is out of range. Choose smaller.")
    if max_r < min_r:
        raise Exception("Start day (" + kind + ") is after end day.")


class HlineInfo:
    def __init__(self, hist_name, hlines, start, end):
        self.hist_name = hist_name
        self.hlines = hlines
        self.start = start
        self.end = end
    #
    # def __repr__(self):
    #     return json.dumps(self.__dict__)


class TimeWindow:
    def __init__(self, start, end, time_format=None):
        """

        :type start: str
        """
        self.start = start
        self.end = end
        self.time_format = time_format


class HistoricalData:

    def __init__(self, name, data_frame, tolerance, density, static_window, dynamic_window, tick):
        self.__name = name
        self.__data_frame = data_frame
        self.__tolerance = tolerance
        self.__density = density
        self.__static_window = static_window
        self.__dynamic_window = dynamic_window
        self.__tick = tick
        self.__reindex_close_hist()

    def get_name(self):
        return self.__name

    def __reindex_close_hist(self):
        self.__data_frame.Close.index = self.__data_frame.CloseTime.values

    def __forward_static_window(self):
        self.__static_window.start = utime.forward_date_time_str(self.__static_window.start, self.__tick,
                                                                 self.__static_window.time_format)
        self.__static_window.end = utime.forward_date_time_str(self.__static_window.end, self.__tick,
                                                               self.__static_window.time_format)

    def __get_close_hist(self):
        return self.__data_frame.Close.loc[self.__static_window.start:self.__static_window.end]

    def get_hlines_info_on_tick(self):
        self.__forward_static_window()
        return self.get_hlines_info()

    def get_hlines_info(self):  # returns hlines based on current static_window
        close_hist = self.__get_close_hist()
        close_points = close_hist.values  # It is new: we have to send points instead of other data structures
        try:
            hlines, exterma = tl.calc_static_slines_mixed(close_points, self.__tolerance, self.__density)
            return HlineInfo(self.__name, hlines, self.__static_window.start, self.__static_window.end)
        except:
            print(f"Exception in calculation of hlines({self.__name}), returning no hlines for the interval: "
                  f"[{self.__static_window.start}, {self.__static_window.end}]")
            print(f"History length: {len(close_points)}")
            return HlineInfo(self.__name, [], self.__static_window.start, self.__static_window.end)

    def get_hlines_info_apc2(self):  # returns hlines based on current static_window based on new approach by Saleh
        close_hist = self.__get_close_hist()
        close_points = close_hist.values  # It is new: we have to send points instead of other data structures
        try:
            hlines, exterma = tl.calc_static_slines_mixed(close_points, self.__tolerance, self.__density)
            return HlineInfo(self.__name, hlines, self.__static_window.start, self.__static_window.end)
        except:
            print(f"Exception in calculation of hlines({self.__name}), returning no hlines for the interval: "
                  f"[{self.__static_window.start}, {self.__static_window.end}]")
            print(f"History length: {len(close_points)}")
            return HlineInfo(self.__name, [], self.__static_window.start, self.__static_window.end)


class DataTracker:

    def __init__(self):
        self.__historical_data_list = []

    def add_historical_data(self, historical_data):
        self.__historical_data_list.append(historical_data)

    def get_all_hlines_info(self):
        all_hlines_info = []
        for historical_data in self.__historical_data_list:
            all_hlines_info.append(historical_data.get_hlines_info())
        return all_hlines_info

    def get_hist_hlines_info_on_tick(self, hist_name):
        def get_historical_data(name):
            for historical_data in self.__historical_data_list:
                if historical_data.get_name() == name:
                    return historical_data
            raise Exception("Invalid historical data name: " + name)

        return get_historical_data(hist_name).get_hlines_info_on_tick()

    def update_hist_data_on_tick(self):
        pass
