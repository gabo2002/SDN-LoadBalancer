import os
import json 

# Get the path of the file
def get_file_path(file, file_name):
    filePath = os.path.dirname(os.path.realpath(file))
    path = os.path.join(filePath, file_name)
    path = os.path.abspath(path)
    return path

# Load the costants from the costants.json file
def load_costants():
    try:
        filePath = os.path.dirname(os.path.realpath(__file__))
        path = os.path.join(filePath, '../config/costants.json')
        file = open(path,'r')
        data = json.load(file)
        file.close()
        return data
    except Exception as e:
        print("Impossible to load the costants.json file")
        print("Error: {}".format(e))
        print("Exiting...")
        exit(1)

costants = load_costants()

def print_debug(message):
    if costants['debug']:
        print("{}  {}DEBUG: {}{}".format(costants['debug_emote'],costants['ansi_yellow'],message,costants['ansi_white']))

def print_error(message):
    print("{}  {}ERROR: {}{}".format(costants['error_emote'],costants['ansi_red'],message,costants['ansi_white']))


def print_path(path,src,dst):
    #nx.shortest_path(self.graph, source=src, target=dst, weight='weight')
    print("Path from {} to {}:".format(src,dst))
    for i in range(len(path)-1):
        print("{} -> ".format(path[i]),end='')

    print(path[-1])