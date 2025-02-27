import os
import logging


log = logging.getLogger("__name__")

valid_topics = {
    "nodered/post/flow": "Post new flow to nodered",
    "nodered/put/flow": "Put new version of existing flow",
    "nodered/get/flow": "Get Full Json of a specified flow",
    "nodered/get/flows": "Get name and vesion of all flows",
    "nodered/delete/flow": "Delete Specified flow",
    "password/put/nodered": "Set password for node-red authentication",
    "logs/get/nodered": "get full current logs from node-red",
    "logs/get/dcp": "get full current logs from DcpMqttClient",
}


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
