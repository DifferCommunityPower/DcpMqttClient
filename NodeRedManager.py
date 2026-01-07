import logging
import requests
import time
import json

from utils import _get_logs

log = logging.getLogger("__name__")


class NrManager:
    def __init__(self):
        self.api_url = "http://localhost:1880/"
        self.sleep_flow_start = 10
        self.status = ""
        self.mqtt_response = ""


    def get_id(self, label):
        url = self.api_url + "flows"
        flows_r = requests.get(url)
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
        flows_id_label_dict:dict[str:str] = {}
        for node in flows:
            label = node.get("label")
            if label:
                id = node.get("id")
                flows_id_label_dict[id] = label
        flow_config_dict:dict[str:list] = {}
        for label in flows_id_label_dict.values():
            flow_config_dict[label] = []
        for node in flows:
            z:str = node.get("z")
            if z:
                label:str = flows_id_label_dict[z]
                flow_config_dict[label].append(node)

        return flow_config_dict


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
        self.action = subtopiclist[1]
        if self.action == "set":
            payload = json.loads(payload)

            label = payload["name"]
            id = self.get_id(label)
            if id:
                url = f"{self.api_url}flow/{id}"
                self.action = "put"
            else:
                self.action = "post"
                
            blob_r = requests.get(payload["url"])
            flow_json = blob_r.json()
            flow_json = self.connect_victron_nodes(blob_r.json())
            if self.status:
                self.action = ""

        if self.action == "post":
            log.debug(f"posting to nodered api on {url}")
            log.debug(f"payload : {flow_json}")

            r = requests.post(url, json=flow_json)
            if r.status_code == 200:
                self.status = "done"
                self.mqtt_response = r.text

            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif self.action == "put":
            log.debug(f"payload : {flow_json}")
            r = requests.put(url, json=flow_json)
            if r.status_code == 200:
                self.status = "done"
                self.mqtt_response = r.text
            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif self.action == "delete":
            r = requests.delete(url=url)
            if r.status_code == 204:
                self.status = "done"
                self.mqtt_response = r.text
            else:
                self.status = "error"
                self.mqtt_response = f"Error from node red api with code: {r.status_code} content:{r.text}"

        elif self.action == "get":
            r = requests.get(url)
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
