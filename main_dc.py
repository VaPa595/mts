import asyncio
import multiprocessing
import queue
from multiprocessing import Process
from time import sleep

import pandas as pd
from mongoengine import connect, disconnect

from finance.analysis.trendstate.trend_state_dc import TrendStateDC, TrendStateConfigDC
from finance.config.config_dc import ConfigReader
from finance.dataprovider.data_provider import DataProvider, DataProviderConfig
from finance.datasource.data_source import DataSource
from finance.datasource.frxpkg.frx_converter import ForexDataConverter
from finance.datasource.frxpkg.frx_downloader import ForexCandleHistDownloader
from finance.datasource.frxpkg.frx_sockets import ForexCandleSocket
from finance.datasource.interface import DSInterfaceRabbitMQ, DSInterfaceMultiProc
from finance.datasource.simdatasource.simserver import start_sim_server_with_socket, \
    start_sim_server_without_socket
from finance.decisioncenter.decision_maker_dc import DecisionConfigDC, DecisionMaker
from finance.market.market import MarketSimulator
from finance.market.trade import TradeStateTrackerConfig, TradeStateTracker
from finance.modules.enums import SIDE_BUY, EXE_OFFLINE_SS_FAST, EXE_OFFLINE_NSS, EXE_ONLINE, EXE_OFFLINE_SS, \
    EXE_ONLINE_SS_Fast
from finance.utilities import utime
from finance.utilities.ubots.bale_bot import BaleBot
from finance.utilities.uio import ulog


# todo (1): it is necessary that save all excel data with column name equal to Candle attributes names


def to_datetime(epoch):
    return utime.epoch_to_utc_datetime(epoch=epoch, datetime_format="%d-%m-%Y %H:%M:%S")


def create_candle_hist_for_socket_server_from_df_hist(config_reader, data_source):  # used for sim_server with socket
    print("Converting df_hist_1m to candle_hist_for_socket_server")
    curr_time = config_reader.get_current_time() - 1
    df_hist_1m = data_source.get_data_frames_dict()["1m"].loc[curr_time:]

    socket_candle_hist = data_source.df_hist_to_socket_candle_hist(df_hist_1m)  # returns list of jsons
    return socket_candle_hist


def create_candle_hist_from_df_hist(config_reader, data_source):  # used for sim_server without socket
    print("Converting df_hist_1m to candle_hist_1m")
    curr_time = config_reader.get_current_time() - 1
    df_hist_1m = data_source.get_data_frames_dict()["1m"].loc[curr_time:]

    candle_hist = data_source.df_hist_to_candle_object_hist(df_hist_1m, '1m')
    return candle_hist


# def create_binance_data_source_online()  # todo (0) binance
# def create_binance_data_source_offline() # todo (0) binance

def create_forex_data_source_online(config_reader):
    candle_socket = ForexCandleSocket(config_reader.get_frx_listener_log_file(), config_reader.get_rwc_log_file())
    raw_data_converter = ForexDataConverter()
    candle_hist_downloader = ForexCandleHistDownloader(raw_data_converter, config_reader.get_symbol())

    return DataSource("RoboForex", candle_socket=candle_socket, candle_hist_downloader=candle_hist_downloader,
                      data_converter=raw_data_converter)


def create_forex_data_source_offline(config_reader):
    hist_file_1m = config_reader.get_hist_file_1m()
    hist_file_small = config_reader.get_hist_file_small()
    hist_file_large = config_reader.get_hist_file_large()

    # data_frame items should be same order as web-socket data
    data_frames_dict = {}

    print(f"Loading excel file 1m...")
    data_frame_1m = pd.read_excel(hist_file_1m, sheet_name='Sheet1', engine='openpyxl')
    data_frame_1m.index = data_frame_1m.OpenTime.values
    data_frames_dict['1m'] = data_frame_1m

    print(f"Loading excel file small...")
    data_frame_small = pd.read_excel(hist_file_small, sheet_name='Sheet1', engine='openpyxl')
    data_frame_small.index = data_frame_small.OpenTime.values
    data_frames_dict['1h'] = data_frame_small

    print(f"Loading excel file 4h...")
    data_frame_large = pd.read_excel(hist_file_large, sheet_name='Sheet1', engine='openpyxl')
    data_frame_large.index = data_frame_large.OpenTime.values
    data_frames_dict['4h'] = data_frame_large

    # End of providing data_frame ------------------------------------------------

    candle_socket = ForexCandleSocket(config_reader.get_frx_listener_log_file(), config_reader.get_rwc_log_file())
    raw_data_converter = ForexDataConverter()
    candle_hist_downloader = ForexCandleHistDownloader(raw_data_converter, config_reader.get_symbol(), data_frames_dict)

    return DataSource("RoboForex", candle_socket=candle_socket, candle_hist_downloader=candle_hist_downloader,
                      data_converter=raw_data_converter)


def start_data_provider(config_reader, hist_1m_queues, hist_1m_df_queues, trend_state_queues, exe_mode,
                        fast_exe_modes, dsi=None):
    # print("DP-process started.")

    # -------- ONLINE TRADING
    def run_online_mode():
        trend_state_config = TrendStateConfigDC(atr_configs=config_reader.get_atr_configs(),
                                                small_interval=config_reader.get_small_interval(),
                                                large_interval=config_reader.get_large_interval(),
                                                log_file=config_reader.get_trend_log_file())
        trend_state_dc = TrendStateDC(trend_state_config)

        dp_config = DataProviderConfig(symbol=config_reader.get_symbol(), market_config=None,
                                       slines_dir=None, hist_1m_days=config_reader.get_hist_1m_days(),
                                       candle_intervals=config_reader.get_candle_intervals(),
                                       big_hist_days=config_reader.get_large_hist_days(),
                                       dp_log_file=config_reader.get_data_provider_log_file(),
                                       db_log_file=config_reader.get_db_log_file())

        data_source = create_forex_data_source_online(config_reader)
        data_provider = DataProvider(dp_config, data_source, trend_state_dc, hist_1m_queues, hist_1m_df_queues,
                                     trend_state_queues, exe_mode, fast_exe_modes)

        data_provider.start('finance_frx_db')  # 'finance_db'  # todo (1) config file

    def run_offline_mode():
        db_name = 'finance_db_test_01'  # todo (1) config file
        db = connect(db_name)
        db.drop_database(db_name)
        disconnect()

        # todo (1) set None for unnecessary configs
        trend_state_config = TrendStateConfigDC(atr_configs=config_reader.get_atr_configs(),
                                                small_interval=config_reader.get_small_interval(),
                                                large_interval=config_reader.get_large_interval(),
                                                log_file=config_reader.get_trend_log_file())
        trend_state_dc = TrendStateDC(trend_state_config)

        dp_config = DataProviderConfig(symbol=config_reader.get_symbol(), market_config=None,
                                       slines_dir=None, hist_1m_days=config_reader.get_hist_1m_days(),
                                       candle_intervals=config_reader.get_candle_intervals(),
                                       big_hist_days=config_reader.get_large_hist_days(),
                                       dp_log_file=config_reader.get_data_provider_log_file(),
                                       db_log_file=config_reader.get_db_log_file())

        data_source = create_forex_data_source_offline(config_reader)
        data_provider = DataProvider(dp_config, data_source, trend_state_dc, hist_1m_queues, hist_1m_df_queues,
                                     trend_state_queues, exe_mode, fast_exe_modes)

        if exe_mode in [EXE_OFFLINE_SS, EXE_OFFLINE_SS_FAST]:  # dsi is not None in EXE_OFFLINE_SS_FAST mode
            # dsi should be of type mpqueue
            raw_hist_1m = create_candle_hist_for_socket_server_from_df_hist(config_reader, data_source)
            host = config_reader.get_wss_host()
            port = config_reader.get_wss_port()
            Process(target=start_sim_server_with_socket, args=(raw_hist_1m, host, port, dsi)).start()
        elif exe_mode == EXE_OFFLINE_NSS:
            candle_hist_1m = create_candle_hist_from_df_hist(config_reader, data_source)
            start_sim_server_without_socket(data_provider, candle_hist_1m, dsi)  # dsi should be of type mpqueue
        else:
            pass  # candles will be send vi another application over web socket

        data_provider.start(db_name)

    if exe_mode == EXE_ONLINE:  # two other online cases are in fact offline. (
        run_online_mode()
    else:
        run_offline_mode()


def start_decision_maker(config_reader, hist_1m_df_queue, trend_state_queue, trade_state_queue, decision_queue,
                         exe_mode):
    # print("DM-process started.")
    decision_config = DecisionConfigDC(small_interval=config_reader.get_small_interval(),
                                       large_interval=config_reader.get_large_interval(),
                                       default_volume=config_reader.get_default_volume(),
                                       buy_trade=config_reader.get_buy_trade_status(),
                                       sell_trade=config_reader.get_sell_trade_status(),
                                       bale_bot_config=config_reader.get_bale_bot_config(),
                                       mpqueue_config=config_reader.get_mpqueue_config(),
                                       log_file=config_reader.get_alg_log_file())

    decision_maker = DecisionMaker(config=decision_config, hist_1m_df_queue=hist_1m_df_queue,
                                   trend_state_queue=trend_state_queue, trade_state_queue=trade_state_queue,
                                   decision_queue=decision_queue, exe_mode=exe_mode)

    decision_maker.start()


def start_trade_state_tracker(market, trade_state_queue):
    """
    :param Market market:
    :param multiprocessing.Queue trade_state_queue:
    """
    cr = ConfigReader("alg_dc.ini")
    tst_config = TradeStateTrackerConfig(bale_bot_config=cr.get_bale_bot_config(),
                                         mpqueue_config=cr.get_mpqueue_config(),
                                         log_file=cr.get_trade_log_file())
    trade_state_tracker = TradeStateTracker(tst_config, market, trade_state_queue)
    trade_state_tracker.start()


async def health_check_loop():
    bale_bot_health = BaleBot(token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')  # todo (1) get from config  # same token and chat id in frxstreamsnew.py
    last_msg_id = None  # ID of last message has been sent from hear. (NOTE: this bot also is used in frxstreamsnew.py)
    while True:
        sleep(1200)
        last_msg_id = await bale_bot_health.send_message(chat_id='4426980252', text="Online", msg_id_to_delete=last_msg_id, delete_last_msg=True)  # todo (1) get from config


def run_health_check_loop():
    asyncio.run(health_check_loop())


def create_date_source_interface(dsi_type):
    """
    :param str dsi_type:
    :return:
    :rtype: finance.datasource.interface.DataSourceInterface
    """
    if dsi_type == 'rmq':  # RabbitMQ
        return DSInterfaceRabbitMQ(exch_name='exch')  # todo (1) config file
    else:  # it is of mpqueue type
        mpqueue = multiprocessing.Queue()
        return DSInterfaceMultiProc(mpqueue)


def main():
    config_reader = ConfigReader("alg_dc.ini")  # todo (2) also get name of config file from a general config file

    fast_exe_modes = [EXE_OFFLINE_SS_FAST, EXE_OFFLINE_NSS, EXE_ONLINE_SS_Fast]  # todo (5): get from config
    logger = ulog.get_default_logger(__name__, config_reader.get_main_log_file())

    exe_mode = EXE_ONLINE_SS_Fast  # EXE_ONLINE, EXE_OFFLINE_SS_FAST, EXE_ONLINE_SS_Fast  # todo (5): get from config

    print(f"*********** MODE = {exe_mode} ***********")

    logger.info("Initializing all processes")
    print("Main: Initializing all processes")

    # ------ INITIALIZING MARKET ------
    market_order_queue = multiprocessing.Queue()  # just in simulation case
    market = MarketSimulator(market_order_queue)

    # ------ INITIALIZING TRADE STATE TRACKER ------
    tst_trade_state_queue = multiprocessing.Queue()
    trade_state_tracker_proc = Process(target=start_trade_state_tracker, args=(market, tst_trade_state_queue))

    # ------ INITIALIZING DECISION MAKER ------
    dm_hist_1m_df_queue = multiprocessing.Queue()
    dm_trend_state_queue = multiprocessing.Queue()
    decision_queue = multiprocessing.Queue()
    decision_maker_proc = Process(target=start_decision_maker,
                                  args=(config_reader, dm_hist_1m_df_queue, dm_trend_state_queue,
                                        tst_trade_state_queue, decision_queue,
                                        exe_mode,))

    # ------ INITIALIZING DATA PROVIDER ------
    hist_1m_queues = []  # See issue #412

    # Some of the classes only needs hist_1m for EMA calculation, so they should get hist_1m_df: (# See issue #412)
    hist_1m_df_queues = [dm_hist_1m_df_queue]
    trend_state_queues = [dm_trend_state_queue]

    # dsi is just for data_provider (offline_without simulated socket server) process to send new candle if only DM is ready.
    dsi = None
    if exe_mode in fast_exe_modes:
        dsi = create_date_source_interface('rmq')  # rmq or mpqueue

    data_provider_proc = Process(target=start_data_provider,
                                 args=(config_reader, hist_1m_queues, hist_1m_df_queues,
                                       trend_state_queues, exe_mode, fast_exe_modes, waiting_queue))

    # ------ INITIALIZING DATA PROVIDER ------
    health_check_process = Process(target=run_health_check_loop)

    # ------ STARTING ALL PROCESSES ------
    print("Main: Starting all processes")
    trade_state_tracker_proc.start()
    decision_maker_proc.start()
    data_provider_proc.start()
    health_check_process.start()

    only_open_alert = config_reader.get_only_open_alert()
    while True:
        try:
            decision = decision_queue.get(block=True, timeout=1)  # todo (5) config (different than other)
            if decision is not None:
                if only_open_alert:
                    log_msg = f"Open({decision.otype}) alert at {to_datetime(epoch=decision.otime)}"
                    logger.info(log_msg)
                    print(log_msg)
                if decision.oside == SIDE_BUY:
                    log_msg = f"ORDER  {decision.otype}: Time: {to_datetime(decision.otime)} - PRC: {decision.price}"
                    logger.info(log_msg)
                    print(log_msg)
                    # order = Order(otype=decision.otype, curr_price=decision.curr_price)
                    # market_order_queue.put(order)
                else:  # oside == SIDE_SELL
                    log_msg = f"ORDER {decision.otype}: Time: {to_datetime(decision.otime)} - PRC: {decision.price}"
                    logger.info(log_msg)
                    print(log_msg)
                    # market_order_queue.put(None)
            if exe_mode in fast_exe_modes:
                dsi.ready_to_receive_next_candle()
        except queue.Empty:
            continue


if __name__ == '__main__':
    main()
