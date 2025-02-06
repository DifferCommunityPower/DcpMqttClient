# cerbo-mqtt-client

This repo is very much work in progress, and is open source primarily to be installable with SetupHelper

### Disclaimer
I'm not responsible for the usage of this script. Use on own risk! 

### Purpose
Execute wanted tasks on the cerbo based on incoming messages on mqtt.
Currently the main functionality is for accesing the local node-red api installing or updating flows from a url provided in the mqtt message.

### Install

Install by adding to SetupHelper (need to be installed first)

### Compatibility
Currently testing with Cerbo GX Mk2, Venus OS version v3.53

### Debugging

The logs can be checked with 
```
tail -n 100 -F /var/log/DcpMqttClient/current | tai64nlocal
```

The service status can be checked with svstat: 
```
svstat /service/DcpMqttClient
```

This will output somethink like ```/service/DcpMqttClient: up (pid 5845) 185 seconds```