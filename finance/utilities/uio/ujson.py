import json
import os

from finance.utilities.uio import uio


# todo determine output
# todo try/catch
# todo better names

def write_dictionary_to_json_file(dictionary, file_name):
    file_abs_path = os.path.join(uio.get_data_dir(), file_name)
    json_object = json.dumps(dictionary, indent=4)  # Serializing json
    uio.write_file(json_object, file_abs_path)


def write_list_to_json_file(list_data, file_abs_path):
    json_object = json.dumps([obj.__dict__ for obj in list_data])
    uio.write_file(json_object, file_abs_path)


def write_obj_to_json_file(obj, file_abs_path):
    json_object = json.dumps(obj.__dict__)
    uio.write_file(json_object, file_abs_path)


def list_to_json(obj_list):
    json_object = json.dumps([obj.__dict__ for obj in obj_list])
    return json_object

