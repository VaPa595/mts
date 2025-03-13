import os
import shutil

# todo determine output
# todo try/catch
# todo always check the project root in each project
from finance.utilities import utime


def get_root_dir():  # todo, find better way (use execution of module on call)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def get_data_dir():
    return os.path.join(get_root_dir(), "data")


def get_log_dir():
    return os.path.join(get_data_dir(), "log")


def get_configs_dir():
    return os.path.join(get_data_dir(), "configs")


def get_config_file():
    data_dir = get_configs_dir()
    return os.path.join(data_dir, "config.ini")


def get_config_file(name):
    data_dir = get_configs_dir()
    return os.path.join(data_dir, name)  # todo: if not exist?


def get_log_file(file_name):
    log_dir = get_log_dir()
    return os.path.join(log_dir, file_name)


def create_folder(directory, folder_name):
    # dir_path = os.path.abspath(os.curdir)
    # folder_complete_path = os.path.join(dir_path, audio_folder, folder_name)
    folder_complete_path = os.path.join(directory, folder_name)
    if not os.path.exists(folder_complete_path):
        os.makedirs(folder_complete_path)
    return folder_complete_path


def copy(file, dest):
    shutil.copy(file, dest)


def load_files(files_dir, extension):
    files = [file for file in os.listdir(files_dir) if file.endswith(extension)]
    return files


def load_abs_files(files_dir, extension):
    abs_files = [os.path.join(files_dir, file) for file in sorted(os.listdir(files_dir), key=len) if
                 file.endswith(extension)]
    return abs_files


def write_file(data, file_abs_path):
    with open(file_abs_path, "w") as outfile:
        outfile.write(data)


def abs_data_file_path(filename):
    return os.path.join(get_data_dir(), filename)


def new_dir_in_data_timed_name():
    return new_dir_in_data(utime.now_for_file_name())


def new_dir_in_data(dir_name):
    try:
        directory = os.path.join(get_data_dir(), dir_name)
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory
    except:
        return None
