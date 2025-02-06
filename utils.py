import os

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

     