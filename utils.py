import os
import subprocess
import logging
log = logging.getLogger("__name__")

def get_id(flows,label):
    for node in flows:
        nodelabel = node.get('label')
        if nodelabel:
            nodelabel = nodelabel.split('-')[0]
        if nodelabel == label:
            return node.get('id')
        
def get_labels(flows):
    flows_list = []
    for node in flows:
        label = node.get('label')
        if label:
            flows_list.append(label)
    return flows_list


def getVersion() -> str:
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)),"version")
    with open(filename) as f:
        return f.read().replace('\n','')

def put_pw_nr(password):
    log.debug(f'Setting Password to {password}')
    with open('/data/conf/dcppassword.txt','w') as f:
        f.write(password)
    os.environ["HOME"] = "/home/root"
    r = subprocess.run("node-red admin hash-pw",input=str(password),shell=True,capture_output=True,text=True)
    hash = r.stdout.split()[1]
    log.debug(r)
    with open('/data/conf/vncpassword.txt','w') as f:
        f.write(hash)
    subprocess.run('killall node-red',shell=True)

def get_pw_nr():
    with open('/data/conf/dcppassword.txt','r') as f:
        return f.read()