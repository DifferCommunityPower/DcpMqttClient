#!/usr/bin/env python
import paho.mqtt.client as mqtt
from gi.repository import GLib  # pyright: ignore[reportMissingImports]
import logging
import sys
import dbus
import requests
import json
import time
from dbus.mainloop.glib import DBusGMainLoop
from utils import (
    get_id,
    get_labels,
    getVersion,
    put_pw_nr,
    get_pw_nr,
    get_errors_nr,
    get_logs_nr,
    get_logs_dcp,
)


# import Victron Energy packages
sys.path.insert(1, "/data/SetupHelper/velib_python")
from vedbus import VeDbusService


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
        self.flow_api_url = "http://localhost:1880/"

        self.dbusservice = DcpDbusClient(self.version)
        self.auth_header = {}

        try:
            self.auth_nr(get_pw_nr()) #Fails here if there is no password set
        except:
            pass

    def auth_nr(self, password):
        auth_data = {
            "client_id": "node-red-admin",
            "grant_type": "password",
            "scope": "*",
            "username": "admin",
            "password": password,
        }
        url = self.flow_api_url + "auth/token"
        try:
            auth_r = requests.post(url=url, json=auth_data)
            try:
                r_dict = auth_r.json()
            except:
                log.info(auth_r)
        except requests.exceptions.RequestException as e:
            return e
        try:
            token = r_dict["access_token"]
            self.auth_header = {"Authorization": f"Bearer {token}"}
        except:
            log.warning(f"Could not get token nr api:{r_dict}")
            # Authentication will fail if on boot if no password is set. Should we ask for password from dcp-mqtt?

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
        topicList = msg.topic.split("/")
        reference_id = topicList[-1]
        subtopiclist = topicList[3:-1]
        log.debug(subtopiclist)
        payload = str(msg.payload.decode("utf-8"))

        if topicList[0] == "dcp":
            if topicList[1] == "teltonika":
                self.dbusservice.post(topicList[1:], payload)

        if subtopiclist[0] == "nodered":
            self.nodered(subtopiclist, reference_id, payload)
        elif subtopiclist[0] == "password":
            self.pw_manager(subtopiclist, reference_id, payload)
        elif subtopiclist[0] == "logs":
            self.logs(subtopiclist, reference_id, payload)

    def nodered(self, subtopiclist, reference_id, flow_url=None):
        path = "/".join(subtopiclist[2:])
        subtopic = "/".join(subtopiclist)
        url = self.flow_api_url + path

        if flow_url:
            blob_r = requests.get(flow_url)

        if len(subtopiclist) > 3:
            # finds the correct local id of the flow for the request if a flow is specified
            if subtopiclist[3] != "state":
                label = subtopiclist[3]
                url = self.flow_api_url + "flows"
                flows_r = requests.get(url, headers=self.auth_header)
                flows = json.loads(flows_r.text)
                id = get_id(flows, label)
                url = f"{self.flow_api_url}flow/{id}"

        if len(subtopiclist) < 2:
            status = "error"
            mqtt_response = "no command given"

        elif subtopiclist[1] == "post":
            log.debug(f"posting to nodered api on {url}")
            log.debug(f"payload : {blob_r.json()}")

            r = requests.post(url, headers=self.auth_header, json=blob_r.json())
            if r.status_code == 200:
                status = "done"
                mqtt_response = r.json()

            else:
                status = "error"
                mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif subtopiclist[1] == "put":
            log.debug(f"payload : {blob_r.json()}")

            try:
                r = requests.put(url, headers=self.auth_header, json=blob_r.json())
                if r.status_code == 200:
                    status = "done"
                    mqtt_response = r.text
                else:
                    status = "error"
                    mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"
            except requests.exceptions.RequestException as e:
                status = "error"
                mqtt_response = f"Error connecting to node red api:{str(e)}"

        elif subtopiclist[1] == "delete":
            try:
                r = requests.delete(url=url, headers=self.auth_header)
                if r.status_code == 204:
                    status = "done"
                    mqtt_response = r.text
                else:
                    status = "error"
                    mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"
            except requests.exceptions.RequestException as e:
                status = "error"
                mqtt_response = f"Error connecting to node red api:{str(e)}"

        elif subtopiclist[1] == "get":
            try:
                r = requests.get(url, headers=self.auth_header)
                if r.status_code == 200:
                    response = r.text
                    if subtopiclist[2] == "flows":
                        flows = json.loads(r.text)
                        response = json.dumps(get_labels(flows))

                    status = "done"
                    mqtt_response = response
                else:
                    status = "error"
                    mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"
            except requests.exceptions.RequestException as e:
                status = "error"
                mqtt_response = f"Error connecting to node red api:{str(e)}"
        # Sleep to wait for nodered restart so we can check for error logs before we respond back
        time.sleep(10)
        logs = get_errors_nr()
        if len(logs):
            status = "error"
            mqtt_response += "There are error logs from node red:"
            for logentry in logs:
                mqtt_response += f"{logentry},"
        self.dbusservice.post(f"/{subtopic}/{reference_id}/{status}", mqtt_response)

    def pw_manager(self, subtopiclist, reference_id, password):
        retry = False
        subtopic = "/".join(subtopiclist)
        if subtopiclist[1] == "put" and subtopiclist[2] == "nodered":
            put_pw_nr(password)
            # Sleep for node-red to restart with new password for authentication
            time.sleep(30)
            while True:
                e = self.auth_nr(get_pw_nr())
                if e:
                    # We get error 111 if node-red is not done restarting
                    if e.errno == 111 and not retry:
                        time.sleep(30)
                    else:
                        status = "error"
                        self.dbusservice.post(
                            f"/{subtopic}/{reference_id}/{status}",
                            f"Error connecting to node red api:{str(e)}",
                        )
                        break
                else:
                    status = "done"
                    self.dbusservice.post(
                        f"/{subtopic}/{reference_id}/{status}", "Password changed"
                    )
                    break

    def logs(self, subtopiclist, reference_id):
        subtopic = "/".join(subtopiclist)
        if len(subtopiclist) < 3:
            status = "error"
            mqtt_response = "Missing commands"
        elif subtopiclist[1] == "get":
            if subtopiclist[2] == "nodered":
                mqtt_response = get_logs_nr()
                status = "done"
            elif subtopiclist[2] == "dcp":
                mqtt_response = get_logs_dcp()
                status = "done"
        self.dbusservice.post(f"/{subtopic}/{reference_id}/{status}", mqtt_response)

    def cleandbus(self):
        self.dbusservice.dbusservice.__del__()
        self.dbusservice = DcpDbusClient(self.version)
        return True


if __name__ == "__main__":
    log.info("Connecting to dbus and mqtt")
    comm = DcpCerboCommunicator()
    DBusGMainLoop(set_as_default=True)
    GLib.timeout_add_seconds(86400, comm.cleandbus)
    GLib.timeout_add_seconds(86400, comm.auth_nr)

    # The GLib mainloop gives space for sending messages on the dbus
    mainloop = GLib.MainLoop()

    # In Subscribe Mqtt an event loop is started for listening to mqtt with loop_start this loop runs in a separate thread
    comm.subscribeMqtt()
    mainloop.run()
