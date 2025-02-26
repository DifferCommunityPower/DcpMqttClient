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
