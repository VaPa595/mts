from collections import deque

from finance.utilities.uio import ulog
from finance.utilities.ufinance import common


class DataBaseInterface:
    __logger = None

    @classmethod
    def init(cls, log_file):
        cls.__logger = ulog.get_default_logger(__name__, log_file)

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
        last_candle = candle_model.objects.order_by('-open_time').first()

        if last_candle is None:
            raise Exception(f"No candle in db {candle_interval}")

        return last_candle

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
