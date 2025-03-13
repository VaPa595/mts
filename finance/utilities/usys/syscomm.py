import os

from finance.utilities.uio.uio import get_root_dir

# os.system(os.path.join(get_root_dir(), "restart_robo.bat"))

import subprocess


def runCmd(*args):
    # p = subprocess.Popen(
    #     *args,
    #     shell=True,
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.STDOUT
    # )
    p = subprocess.Popen(
        *args,
        shell=False,
        stdin=None,
        stdout=None,
        stderr=None
    )
    out, error = p.communicate()
    return out, error


def reset_robo_forex():
    runCmd(os.path.join(get_root_dir(), "restart_robo.bat"))
    # subprocess.call(os.path.join(get_root_dir(), "restart_robo.bat"))

    # os.popen(os.path.join(get_root_dir(), "restart_robo.bat")).read()

