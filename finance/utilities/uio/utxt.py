import os

from BinanceApi.utilities.uio import uio


def write_txt_to_file(txt, file_name):
    file_abs_path = os.path.join(uio.get_data_dir(), file_name)
    uio.write_file(txt, file_abs_path)
