# multiprocessing utilities
import queue


def get_from_queue(q, timeout=None):
    """
    :param multiprocessing.Queue q:
    :param float timeout:
    :return:
    :rtype:
    """
    while True:
        try:
            data = q.get(block=True, timeout=timeout)
            return data
        except queue.Empty:
            continue


