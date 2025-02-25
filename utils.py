import os
import logging


log = logging.getLogger("__name__")

valid_topics = [{"topic":"nodered/post/flow","comment":"Post new flow to nodered"},{}]

def getVersion() -> str:
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), "version")
    with open(filename) as f:
        return f.read().replace("\n", "")


def _get_logs(filename: str):
    with open(filename, "r") as f:
        return f.readlines()


def get_logs_nr():
    return _get_logs("/data/log/node-red-venus/current")


def get_logs_dcp():
    return _get_logs("/data/log/DcpMqttClient/current")
