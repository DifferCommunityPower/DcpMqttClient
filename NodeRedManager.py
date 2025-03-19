import os
import subprocess
import logging
import requests
import time
import json

from utils import _get_logs

log = logging.getLogger("__name__")


class NrManager:
    def __init__(self):
        self.auth_header = {}
        self.api_url = "http://localhost:1880/"
        self.pwd = self.get_pw()
        self.duplicate_pwd = False
        self.sleep_flow_start = 10
        self.status = ""
        self.mqtt_response = ""

        if self.pwd:
            self.auth(self.pwd)
        else:
            log.warning("No password set for node-red")

    def auth(self, password):
        auth_data = {
            "client_id": "node-red-admin",
            "grant_type": "password",
            "scope": "*",
            "username": "admin",
            "password": password,
        }
        url = self.api_url + "auth/token"
        auth_r = requests.post(url=url, json=auth_data)
        r_dict = auth_r.json()
        if auth_r.status_code == 200:
            token = r_dict["access_token"]
            self.auth_header = {"Authorization": f"Bearer {token}"}
            return True
        else:
            log.warning(f"Could not get token nr api:{r_dict}")

    def get_id(self, label):
        url = self.api_url + "flows"
        flows_r = requests.get(url, headers=self.auth_header)
        flows = json.loads(flows_r.text)
        for node in flows:
            nodelabel:str = node.get("label")
            if nodelabel:
                nodelabel_list = nodelabel.split("-")[:-1]
                nodelabel = "-".join(nodelabel_list)
            if nodelabel == label:
                return node.get("id")
        return None

    def get_labels(self, flows):
        flows_list = []
        for node in flows:
            label = node.get("label")
            if label:
                flows_list.append(label)
        return flows_list

    def put_pw(self, password):
        if self.pwd == password:
            self.duplicate_pwd = True
        else:
            self.duplicate_pwd = False
            log.debug(f"Setting Password to {password}")
            with open("/data/conf/dcppassword.txt", "w") as f:
                f.write(password)
            self.pwd = password
            # Home environment has to be set for node-red admin api
            # When running as a srvice we have no home environment as default
            os.environ["HOME"] = "/home/root"
            r = subprocess.run(
                "node-red admin hash-pw",
                input=str(password),
                shell=True,
                capture_output=True,
                text=True,
            )
            hash = r.stdout.split()[1]
            log.debug(r)
            with open("/data/conf/vncpassword.txt", "w") as f:
                f.write(hash)

    def restart(self, sleep_after_kill=30):
        subprocess.run("killall node-red", shell=True)
        time.sleep(sleep_after_kill)

    def get_pw(self):
        try:
            with open("/data/conf/dcppassword.txt", "r") as f:
                return f.read()
        except:
            return None

    def get_errors(self):
        logs: list[str] = []
        lines = _get_logs("/data/log/node-red-venus/current")
        lines.reverse()
        for line in lines:
            log.info(f"Checking line for error:{line}")
            if line.find("error") != -1:
                logs.append(line)
            elif line.find("Starting") != -1:
                break

        return logs

    def handle_message(self, subtopiclist, payload=None):
        self.status = ""
        self.mqtt_response = ""
        path = "/".join(subtopiclist[2:])
        url = self.api_url + path
        action = subtopiclist[1]
        if payload:
            payload = json.loads(payload)
            if "name" in payload:
                label = payload["name"]
                id = self.get_id(label)
                if id:
                    url = f"{self.api_url}flow/{id}"
                    action = "put"
                else:
                    action = "post"
                
            if "url" in payload:
                blob_r = requests.get(payload["url"])
                flow_json = self.connect_victron_nodes(blob_r.json())
                if self.status:
                    action = ""

        if action == "post":
            log.debug(f"posting to nodered api on {url}")
            log.debug(f"payload : {flow_json}")

            r = requests.post(url, headers=self.auth_header, json=flow_json)
            if r.status_code == 200:
                self.status = "done"
                self.mqtt_response = r.text

            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif action == "put":
            log.debug(f"payload : {flow_json}")
            r = requests.put(url, headers=self.auth_header, json=flow_json)
            if r.status_code == 200:
                self.status = "done"
                self.mqtt_response = r.text
            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif action == "delete":
            r = requests.delete(url=url, headers=self.auth_header)
            if r.status_code == 204:
                self.status = "done"
                self.mqtt_response = r.text
            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif action == "get":
            r = requests.get(url, headers=self.auth_header)
            if r.status_code == 200:
                response = r.text
                if subtopiclist[2] == "flows":
                    flows = json.loads(r.text)
                    response = json.dumps(self.get_labels(flows))

                self.status = "done"
                self.mqtt_response = response
            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"
        # Sleep to wait for nodered flow to go live so we can check for error logs before we respond back
        time.sleep(self.sleep_flow_start)
        logs = self.get_errors()
        if len(logs):
            self.status = "error"
            self.mqtt_response += "There are error logs from node red:"
            self.mqtt_response += json.dumps(logs)

        return [self.status, self.mqtt_response]

    def connect_victron_nodes(self, flow: dict):
        nodes: list[dict] = flow["nodes"]
        for node in nodes:
            node_type: str = node["type"]
            if node_type.count("victron-"):
                url_type = node_type[8:]

                node_service = requests.get(
                    self.api_url + "victron/services/" + url_type,
                    headers=self.auth_header,
                )
                log.debug(len(node_service.json()))
                log.debug(node_service.json())
                if len(node_service.json()) > 0:
                    node_service_json = node_service.json()[0]
                    node["service"] = node_service_json["service"]
                    node["serviceObj"] = {
                        "service": node_service_json["service"],
                        "name": node_service_json["name"],
                    }
                    paths = node_service_json["paths"]
                    for path in paths:
                        if path["path"] == node["path"]:
                            node["pathObj"] = path
                    log.debug(flow)
                else:
                    self.status = "error"
                    self.mqtt_response = (
                        f"could not find victron device for node {node_type}"
                    )


        return flow
