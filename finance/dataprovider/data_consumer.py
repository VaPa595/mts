from abc import ABC, abstractmethod


# def on_new_hist_1m(self, hist_1m):
#     self.hist_candles_1m = hist_1m

class HistConsumer(ABC):  # todo: better structure
    @abstractmethod
    def on_new_hist(self, candle_interval, history):  # todo: rename, only one candle is changed.
        pass


class FullConsumer(ABC):  # todo: better name
    # todo: think to separate full consumers based on candle interval (as parameter)
    @abstractmethod
    def on_new_tick(self, candle_interval, hist_list, trend_state):  # may never be used
        pass




