from abc import ABC, abstractmethod


class TrendState(ABC):

    @abstractmethod
    def __init__(self, config):
        """

        :param TrendStateConfig config:
        """

    @abstractmethod
    def init(self, data_provider):
        """
        :param finance.dataprovider.data_provider.DataProvider data_provider:
        """
        pass

    @abstractmethod
    def update(self, curr_time, hist_1m_df):
        pass

    # This is meaningless, no need to define a private method as an abstract class hear
    # @abstractmethod
    # def __on_new_ticks(self, ticks):
    #     pass

