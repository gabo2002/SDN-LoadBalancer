import os
import json 
import socket 

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


def port_scan(ip,port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)

        result = s.connect((ip,port))
        s.close()
        return True
    except Exception as e:
        return False

def bytes_to_kilobytes(bytes):
    return bytes / 2**10