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
        url = f"{self.api_url}flow/{id}"
        for node in flows:
            nodelabel = node.get("label")
            if nodelabel:
                nodelabel = nodelabel.split("-")[0]
            if nodelabel == label:
                return node.get("id")

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
        for line in lines:
            log.info(f"Checking line for error:{line}")
            if line.find("error") != -1:
                logs.append(line)
            elif line.find("Starting") != -1:
                break

        return logs
    
    def handle_message(self, subtopiclist, flow_url=None):
        path = "/".join(subtopiclist[2:])
        url = self.api_url + path
        action = subtopiclist[1]

        if flow_url:
            blob_r = requests.get(flow_url)

        if len(subtopiclist) > 3:         # finds the correct local id of the flow for the request if a flow is specified
            label = subtopiclist[3]
            id = self.get_id(label)
            url = f"{self.api_url}flow/{id}"

        elif action == "post":
            log.debug(f"posting to nodered api on {url}")
            log.debug(f"payload : {blob_r.json()}")

            r = requests.post(url, headers=self.auth_header, json=blob_r.json())
            if r.status_code == 200:
                self.status = "done"
                self.mqtt_response = r.json()

            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif action == "put":
            log.debug(f"payload : {blob_r.json()}")
            r = requests.put(url, headers=self.auth_header, json=blob_r.json())
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
        
        return [self.status,self.mqtt_response]
