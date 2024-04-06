import json
from mininet.topo import Topo
'''
    Switch json configuration: 

    {
        "switches": [
                {
                    id: int,
                    connectedHost: [int],
                    connectedSwitch: [int],
                },
                {
                    id: int,
                    connectedHost: [int],
                    connectedSwitch: [int],
                }
            ]
    }
    
'''
# Create a class called NetworkTopology that inherits from the Topo class in Mininet, it represents the network topology
class NetworkTopology(Topo):

    def __init__(self, json_path):
        self.json_path = json_path
        Topo.__init__(self)

    # Build the network topology by initializing the switches, hosts, and links 
    # This method is called by the Mininet object when it is created
    def build(self):
        try:
            self.init_topology()
        except Exception as e:
            print("Error: {}".format(e))
            print("Traceback: {}".format(e.with_traceback()))
            print("Exiting...")
            exit(1)

    # Initialize the network topology by reading the JSON file and creating the switches, hosts, and links
    def init_topology(self):
        json_data = self.load_json()

        # Create switches
        self.my_switches = list()
        self.my_hosts = list()

        for switch in json_data['switches']:
            switch_id = str(switch['id'])
            print("Creating switch {}".format(switch_id))
            self.my_switches.append(self.addSwitch(switch_id))

            # Create hosts
            for host_id in switch['hosts']:
                #check if host already exists
                host_id = str(host_id)
                if host_id in self.hosts():
                    self.addLink(host_id, self.my_switches[-1])
                    continue
                
                host = self.addHost(host_id)
                self.my_hosts.append(host)
                print("Creating host {} linked to switch: {}".format(host_id,switch_id))
                self.addLink(host, self.my_switches[-1])
            
        #create switch links
        for switch in json_data['switches']:
            switch_id = str(switch['id'])
            for connected_switch in switch['connected_switches']:
                connected_switch_id = str(connected_switch)
                print("Connecting switch {} to switch {}".format(switch_id, connected_switch_id))
                self.addLink(switch_id, connected_switch_id)

    # Load the JSON network topology file and validate it
    def load_json(self):
        json_file = open(self.json_path, 'r')
        json_data = json.load(json_file)

        #validate json
        if 'switches' not in json_data or list(json_data.keys()) != ['switches']:
            print("Invalid JSON file: 'switches' key not found or extra keys found")
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
                print("The switch with id {} is not unique".format(switch['id']))
                raise Exception('Switch id not unique')
            switch_ids.add(switch['id'])

        #redundant switch connections
        links = set()
        for switch in json_data['switches']:
            for connected_switch in switch['connected_switches']:
                link = (switch['id'], connected_switch)
                if link in links or (link[1], link[0]) in links:
                    print("The link between switch {} and switch {} is redundant".format(link[0], link[1]))
                    raise Exception('Redundant switch connections')
                links.add(link)

        return json_data