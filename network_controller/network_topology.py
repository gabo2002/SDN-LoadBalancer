import json
import traceback
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.node import Host
import utils
from utils import print_debug,print_error

costants = utils.load_costants()

# Create a class called NetworkTopology that inherits from the Topo class in Mininet, it represents the network topology
class NetworkTopology(Topo):

    def __init__(self):
        self.json_path = utils.get_file_path(__file__, "../config/{}/switches.json".format(costants['topology_folder_location']))
        print("\n\n{}  {}NETWORK TOPOLOGY {} Inizializing custom network topology from config file located in: {}{}{}\n\n".format(costants['net_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_blue'], self.json_path, costants['ansi_white']))
        Topo.__init__(self)


    # Build the network topology by initializing the switches, hosts, and links 
    # This method is called by the Mininet object when it is created
    def build(self):
        try:
            self.init_topology()
            print("\n\n{}  {}NETWORK TOPOLOGY {} Network topology initialized{}".format(costants['net_emote'], costants['ansi_green'],costants['ansi_white'],costants['ansi_white']))
        except Exception as e:
            print_error(str(e))
            print_error("Traceback: {}".format(traceback.format_exc()))
            print_error("Exiting...")
            exit(1)

    # Initialize the network topology by reading the JSON file and creating the switches, hosts, and links
    def init_topology(self):
        json_data = self.load_json()

        # Create switches
        self.my_switches = list()
        self.my_hosts = list()

        for switch in json_data['switches']:
            switch_id = str(switch['id'])
            print_debug("Creating switch {}".format(switch_id))
            self.my_switches.append(self.addSwitch(switch_id))

            # Create hosts
            for host in switch['hosts']:
                #check if host already exists
                host_id = str(host['hostid'])
                link_bw_h = int(host['bw'])
                host_ip = str(host['ip'])
                if host_id in self.hosts():
                    self.addLink(host_id, self.my_switches[-1], cls=TCLink, bw=link_bw_h)
                    continue
                
                host = self.addHost(host_id,cls=Host,ip=host_ip, defaultRoute = None)
                self.my_hosts.append(host)
                print_debug("Creating host {} linked to switch: {}".format(host_id,switch_id))
                self.addLink(host, self.my_switches[-1])
            
        #create switch links
        for switch in json_data['switches']:
            switch_id = str(switch['id'])
            for connected_switch in switch['connected_switches']:
                connected_switch_id = str(connected_switch['switchid'])
                link_bw_s = int(connected_switch['bw'])
                print_debug("Connecting switch {} to switch {}".format(switch_id, connected_switch_id))
                self.addLink(switch_id, connected_switch_id, cls=TCLink, bw=link_bw_s)

    # Load the JSON network topology file and validate it
    def load_json(self):
        json_file = open(self.json_path, 'r')
        json_data = json.load(json_file)

        #validate json
        if 'switches' not in json_data or list(json_data.keys()) != ['switches']:
            print_error("Invalid JSON file: 'switches' key not found or extra keys found")
            raise Exception('Invalid JSON file')
        
        for switch in json_data['switches']:    #check if all keys are valid
            keys = switch.keys()
            for key in keys:
                if key not in ['id', 'hosts', 'connected_switches']:
                    raise Exception('Invalid JSON file')

        #Unique switch ids
        switch_ids = set()
        for switch in json_data['switches']:
            if switch['id'] in switch_ids:
                print_error("The switch with id {} is not unique".format(switch['id']))
                raise Exception('Switch id not unique')
            switch_ids.add(switch['id'])

        #redundant switch connections
        links = set()
        for switch in json_data['switches']:
            for connected_switch in switch['connected_switches']:
                link = (switch['id'], connected_switch['switchid'])
                if link in links or (link[1], link[0]) in links:
                    print_error("The link between switch {} and switch {} is redundant".format(link[0], link[1]))
                    raise Exception('Redundant switch connections')
                links.add(link)
        
        #validate hosts
        for switch in json_data['switches']:
            for host in switch['hosts']:
                keys = host.keys()
                for key in keys:
                    if key not in ['hostid', 'ip', 'bw']:
                        print_error("Invalid JSON file: invalid key found: {} should not be here".format(key))
                        raise Exception('Invalid JSON file')
                
                if len(host.keys()) != 3:
                    print_error("Invalid JSON file: missing keys in host")
                    raise Exception('Invalid JSON file')

                if host['bw'] <= 0:
                    print_error("Invalid JSON file: invalid bandwidth: {}".format(host['bw']))
                    raise Exception('Invalid JSON file')

        return json_data