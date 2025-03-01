#!/usr/bin/env python
import paho.mqtt.client as mqtt
from gi.repository import GLib  # type: ignore
import logging
import sys
import dbus  # type: ignore
from dbus.mainloop.glib import DBusGMainLoop  # type: ignore
from NodeRedManager import NrManager
from utils import (
    getVersion,
    get_logs_nr,
    get_logs_dcp,
    valid_topics
)


# import Victron Energy packages
sys.path.insert(1, "/data/SetupHelper/velib_python")
from vedbus import VeDbusService  # type: ignore


class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


def dbusconnection():
    return SystemBus()


logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("__name__")


class DcpDbusClient:
    def __init__(self, version):
        DBusGMainLoop(set_as_default=True)
        self.dbusservice = VeDbusService("com.victronenergy.dcp", dbusconnection())
        self.dbusservice.add_mandatory_paths(
            processname="dcp",
            processversion="1.0",
            connection="none",
            productid=1,
            deviceinstance="0",
            productname="dcp",
            firmwareversion=version,
            hardwareversion="0",
            connected="1",
        )

        self.paths = []

    def post(self, path, msg):
        if path not in self.dbusservice:
            self.dbusservice.add_path(path, 0)
            self.paths.append(path)

        self.dbusservice[path] = msg
        log.debug(f"Posted on dbus path:{path} message:{msg}")


class DcpCerboCommunicator:
    def __init__(self):
        self.mqttc = mqtt.Client()
        self.mqttc.connect("localhost")
        self.version = getVersion()

        self.dbusservice = DcpDbusClient(self.version)
        self.nr = NrManager()

        self.status = ""
        self.mqtt_response = ""

    def subscribeMqtt(self):
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                log.info("Connected to mqtt")

        self.mqttc.on_connect = on_connect
        self.mqttc.on_message = self.on_message
        self.mqttc.subscribe("W/+/dcp/#")

        self.mqttc.subscribe("dcp/teltonika/#")
        self.mqttc.loop_start()

    def on_message(self, client, userdata, msg):
        topic_list = msg.topic.split("/")
        reference_id = topic_list[-1]
        subtopiclist = topic_list[3:-1]
        log.debug(subtopiclist)
        payload = str(msg.payload.decode("utf-8"))

        check_topic = subtopic = "/".join(topic_list[3:6])
        if topic_list[0] == "dcp":# These topics are for local services wanting to post on to dbus 
                if topic_list[1] == "teltonika":
                    self.dbusservice.post(topic_list[1:], payload)
        else: # This is for requests from dcp-mqtt
            log.debug("Message from dcp-mqtt")
            if check_topic in valid_topics.keys():
                cmd_group = subtopiclist[0]

                if cmd_group == "nodered":
                    self.nr.handle_message(subtopiclist, payload)
                    self.mqtt_response = self.nr.mqtt_response
                    self.status=self.nr.status
                elif cmd_group == "password":
                    self.pw_manager(subtopiclist, payload)
                elif cmd_group == "logs":
                    self.logs(subtopiclist)
                subtopic = "/".join(subtopiclist)
            else:
                self.status = "error"
                self.mqtt_response = "Subtopic not valid"
            if self.status:
                self.dbusservice.post(
                        f"/{subtopic}/{reference_id}/{self.status}", self.mqtt_response
                    )


    def pw_manager(self, subtopiclist, password):
        log.debug("password manager started")
        action = subtopiclist[1]
        if action == "put" and subtopiclist[2] == "nodered":
            log.debug("putting password")
            self.nr.put_pw(password)
            if not self.nr.duplicate_pwd:
                self.nr.restart()
                success = self.nr.auth(self.nr.get_pw())
            else:
                success = True

            if success:
                self.status = "done"
                self.mqtt_response = "Password changed"
                log.debug("Password changed")
            else:
                self.status = "error"
                log.debug("Error changing password")

    def logs(self, subtopiclist):
        if subtopiclist[2] == "nodered":
            self.mqtt_response = get_logs_nr()
            self.status = "done"
        elif subtopiclist[2] == "dcp":
            self.mqtt_response = get_logs_dcp()
            self.status = "done"

    def cleandbus(self):
        self.dbusservice.dbusservice.__del__()
        self.dbusservice = DcpDbusClient(self.version)
        return True


if __name__ == "__main__":
    log.info("Connecting to dbus and mqtt")
    comm = DcpCerboCommunicator()
    DBusGMainLoop(set_as_default=True)
    GLib.timeout_add_seconds(86400, comm.cleandbus)
    GLib.timeout_add_seconds(86400, comm.nr.auth)

    # The GLib mainloop gives space for sending messages on the dbus
    mainloop = GLib.MainLoop()

    # In Subscribe Mqtt an event loop is started for listening to mqtt with loop_start this loop runs in a separate thread
    comm.subscribeMqtt()
    mainloop.run()
