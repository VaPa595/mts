import multiprocessing
import queue
import time
from multiprocessing import Process

import pandas as pd
from mongoengine import connect, disconnect

from finance.analysis.trendstate.trend_state_brk import TrendStateConfigBrk
from finance.apps.trader import SocketBasedDataConsumer
from finance.config.config_brk import ConfigReader
from finance.dataprovider.data_provider import DataProvider, DataProviderConfig
from finance.decisioncenter.decision_maker_brk import DecisionMaker, DecisionConfigBrk
from finance.market.market import MarketSimulator
from finance.market.trade_state_brk import TradeStateTracker, TradeStateTrackerConfig
from finance.models.candles import Candle1m
from finance.modules.enums import EXE_FAST, EXE_NORMAL, SIDE_BUY
from finance.utilities import utime
from finance.utilities.uio import ulog
# from finance.utilities.utime import TicToc
from finance.utilities.utime import TicToc


def start_data_provider(hist_1m_queues, hist_1m_df_queues, trend_state_queues, exe_mode, waiting_queue=None):
    # print("DP-process started.")
    symbol = 'BTCUSDT'  # todo (2) config

    cr = ConfigReader("alg_brk.ini")

    # -------- ONLINE TRADING
    # IMP: SET EXE_NORMAL in main
    # data_source = "Binance"  # or "DataFrame"
    # data_provider = DataProvider(symbol, data_source, None, api_key, api_secret, ema_configs, breaking_configs,
    #                              hlines_configs, hlines_dir, hist_1m_queues, hist_1m_df_queues,trend_state_queues,
    #                              exe_mode)
    #
    # data_provider.start()

    # -------- SIMULATED ONLINE TRADING, no need to api_key and api_secret
    # IMP: SET EXE_FAST in main
    data_source = "DataFrame"  # or "Binance"

    db = connect('finance_db_test_01')
    db.drop_database('finance_db_test_01')
    disconnect()

    # data_frame items should be same order as web-socket data
    all_data_frames_dict = {}
    for candle_interval in ["1m", "15m", "1h", "4h"]:  # todo (2) flexible to config
        hist_file = cr.get_hist_file(candle_interval)
        print(f"Loading excel file {candle_interval}...")
        data_frame = pd.read_excel(hist_file, sheet_name='Sheet', engine='openpyxl')
        data_frame.index = data_frame.OpenTime.values
        all_data_frames_dict[candle_interval] = data_frame

    trend_state_config = TrendStateConfigBrk(ema_configs=cr.get_ema_configs(),
                                             breaking_configs=cr.get_breaking_configs(),
                                             slines_configs=cr.get_slines_configs(),
                                             bale_bot_config=cr.get_bale_bot_config(), log_file=cr.get_trend_log_file())
    dp_config = DataProviderConfig(symbol=symbol, market_config=cr.get_market_config(),
                                   trend_state_config=trend_state_config,
                                   slines_dir=cr.get_lines_dir(), hist_1m_days=cr.get_hist_1m_days(),
                                   candle_intervals=cr.get_candle_intervals(),
                                   big_hist_days=cr.get_large_hist_days(),
                                   dp_log_file=cr.get_data_provider_log_file())
    data_provider = DataProvider(dp_config, data_source, all_data_frames_dict, hist_1m_queues, hist_1m_df_queues,
                                 trend_state_queues, exe_mode)

    hist_consumer = SocketBasedDataConsumer()
    data_provider.add_hist_consumer(hist_consumer)
    curr_time = utime.utc_datetime_to_epoch("2022.02.04 00:00:00", "%Y.%m.%d %H:%M:%S")  # new data
    # curr_time = utime.utcdatetime_to_epoch("2021.07.30 00:00:00", "%Y.%m.%d %H:%M:%S")

    data_provider.start_test("finance_db_test_01", curr_time)

    # todo (2):
    #  Sending packets, it should be implemented as socket server sending data to clients, so no need define additional
    #  call-back method in DataProvider
    # last saved candle open_time is June 30, 2021 11:59:00 PM, So:
    hist_1m_to_send = all_data_frames_dict["1m"].loc[curr_time:].to_numpy()

    full_candle = hist_1m_to_send[0]
    simple_candle = Candle1m(open=full_candle[1], high=full_candle[2], low=full_candle[3],
                             close=full_candle[4], volume=full_candle[5], open_time=full_candle[0],
                             close_time=full_candle[6])
    data_provider.on_new_candle_1m_sim(simple_candle)  # todo (2) IMP-check new_candle and 2 days
    time.sleep(5)  # (COMMENT AFTER LONG TIME: why is this necessary while using waiting_queue)

    print("#################################################################")
    print("######################## SENDING CANDLES ########################")
    tic_toc = TicToc()
    for full_candle in hist_1m_to_send[1:, :]:
        tic_toc.tic()
        if waiting_queue is not None:
            waiting_queue.get()

        simple_candle = Candle1m(open=full_candle[1], high=full_candle[2], low=full_candle[3],
                                 close=full_candle[4], volume=full_candle[5], open_time=full_candle[0],
                                 close_time=full_candle[6])
        # tic_toc.tic()

        # if simple_candle.close_time == 1627969019999:
        #     print("Should Close SELL")
        # if simple_candle.close_time == 1626154499999:  # 1625111999999:
        #     print("Should Open SELL")

        data_provider.on_new_candle_1m_sim(simple_candle)
        print(tic_toc.toc())
        # time.sleep(0.2)
        # print(simple_candle.close_time)

    print("#################################################################")
    print("All candles 1m are sent.")


def start_decision_maker(hist_1m_df_queue, trend_state_queue, trade_state_queue, decision_queue, exe_mode):
    # print("DM-process started.")
    cr = ConfigReader("alg_brk.ini")
    decision_config = DecisionConfigBrk(general_config=cr.get_trade_decision_general_config(),
                                        buy_opening_config=cr.get_buy_opening_config(),
                                        sell_opening_config=cr.get_sell_opening_config(),
                                        buy_closing_config=cr.get_buy_closing_config(),
                                        sell_closing_config=cr.get_sell_closing_config(),
                                        bale_bot_config=cr.get_bale_bot_config(),
                                        mpqueue_config=cr.get_mpqueue_config())

    decision_maker = DecisionMaker(config=decision_config, hist_1m_df_queue=hist_1m_df_queue,
                                   trend_state_queue=trend_state_queue, trade_state_queue=trade_state_queue,
                                   decision_queue=decision_queue, exe_mode=exe_mode)

    decision_maker.start()


def start_trade_state_tracker(market, hist_1m_df_queue, trade_state_queue, exe_mode):
    """
    :param Market market:
    :param multiprocessing.Queue hist_1m_df_queue:
    :param multiprocessing.Queue trade_state_queue:
    :param str exe_mode:
    """
    cr = ConfigReader("alg_brk.ini")
    trade_state_tracker_config = TradeStateTrackerConfig(trade_config=cr.get_trade_config(),
                                                         bale_bot_config=cr.get_bale_bot_config(),
                                                         mpqueue_config=cr.get_mpqueue_config(),
                                                         log_file=cr.get_trade_log_file())
    trade_state_tracker = TradeStateTracker(trade_state_tracker_config, market, hist_1m_df_queue, trade_state_queue,
                                            exe_mode)
    trade_state_tracker.start()


def to_datetime(epoch):
    return utime.epoch_to_utc_datetime(epoch=epoch, datetime_format="%d-%m-%Y %H:%M:%S")


def main():
    exe_mode = EXE_FAST  # EXE_FAST
    print("Main process started")
    logger = ulog.get_default_logger(__name__, "main.log")  # todo (5): get from config

    # Important: don't send init hist to websocket

    # trader = Trader(symbol, api_key=api_key, api_secret=api_secret, data_provider=data_provider)
    # trader.start()
    market_order_queue = multiprocessing.Queue()  # just in simulation case
    market = MarketSimulator(market_order_queue)
    tst_hist_1m_df_queue = multiprocessing.Queue()
    tst_trade_state_queue = multiprocessing.Queue()

    trade_state_tracker_proc = Process(target=start_trade_state_tracker,
                                       args=(market, tst_hist_1m_df_queue, tst_trade_state_queue, exe_mode))
    trade_state_tracker_proc.start()

    dm_hist_1m_df_queue = multiprocessing.Queue()
    dm_trend_state_queue = multiprocessing.Queue()
    decision_queue = multiprocessing.Queue()
    decision_maker_proc = Process(target=start_decision_maker, args=(dm_hist_1m_df_queue, dm_trend_state_queue,
                                                                     tst_trade_state_queue, decision_queue,
                                                                     exe_mode,))
    decision_maker_proc.start()

    hist_1m_queues = []  # See issue #412

    # Some of the classes only needs hist_1m for EMA calculation, so they should get hist_1m_df: (# See issue #412)
    hist_1m_df_queues = [tst_hist_1m_df_queue, dm_hist_1m_df_queue]
    trend_state_queues = [dm_trend_state_queue]

    # waiting_queue is just for dp process to send new candle in simulation only DM is done.
    # For online execution set it to None.
    waiting_queue = multiprocessing.Queue()

    data_provider_proc = Process(target=start_data_provider, args=(hist_1m_queues, hist_1m_df_queues,
                                                                   trend_state_queues, exe_mode, waiting_queue))
    data_provider_proc.start()

    while True:
        try:
            decision = decision_queue.get(block=True, timeout=1)  # todo (5) config (different than other)
            if decision is not None:
                if decision.action == "OPEN":
                    if decision.oside == SIDE_BUY:
                        msg = f"ORDER  {decision.otype}: Time: {to_datetime(decision.otime)} - PRC: {decision.price}"
                        print(msg)
                        # logger.info(msg)
                        # order = Order(otype=decision.otype, curr_price=decision.curr_price)
                        # market_order_queue.put(order)
                    else:  # oside == SIDE_SELL
                        msg = f"ORDER {decision.otype}: Time: {to_datetime(decision.otime)} - PRC: {decision.price}"
                        print(msg)
                        # logger.info(msg)
                        # market_order_queue.put(None)
            if exe_mode != EXE_NORMAL:
                waiting_queue.put(1)
        except queue.Empty:
            continue


if __name__ == '__main__':
    main()
