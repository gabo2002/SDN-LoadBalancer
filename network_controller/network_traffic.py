from utils import costants, print_debug, print_error,get_file_path,bytes_to_kilobytes
import json
import traceback

'''
{
    "traffic": [
        {
            "type" : "TCP"/"UDP"/"ARP"

            "src_host": "same name as switches.json
            "dst_host": "same name as switches.json
            "src_port: "port number"
            "dst_port: "port number"
            "data_sixze": "data size in bytes"
        }
    ]
}
'''

class NetworkTraffic:
    def __init__(self, network_controller,topology):
        self.network_controller = network_controller
        self.topology = topology
        self.max_ping = 15
        self.ping_timeout = 0.2

        #load traffic from json
        try:
            path = get_file_path(__file__ , "../config/traffic.json")
            self.load_json(path)
        except Exception as e:
            print_error("Received exception {} while loading traffic from JSON file".format(str(e)))
            print_error("Traceback: {}".format(traceback.format_exc()))
            print_error("Exiting...")
            exit(1)

    def ping_all(self):
        print("\n\n{}  {}NETWORK TRAFFIC {} Performing Reachability Test{}\n\n".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_white']))

        attemps = 0
        drop_rate = 100.0

        while attemps < self.max_ping and drop_rate != 0.0:
            print("\n\n{}  {}NETWORK TRAFFIC {} Ping all hosts attempt: {}{}\n\n".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],attemps+1,costants['ansi_white']))
            drop_rate = self.network_controller.pingAll(timeout=self.ping_timeout)
            attemps += 1

            if drop_rate != 0.0:
                print_error("Drop rate: {}%".format(drop_rate))

            else: 
                print("\n\n{}  {}NETWORK TRAFFIC {} All hosts reachable{}\n\n".format(costants['ping_emote'], costants['ansi_green'],costants['ansi_white'],costants['ansi_white']))
                return
            self.ping_timeout += 0.05
        
        print_error("Not all hosts are reachable: be sure that the controller is running and the network is correctly configured")
        print("\n\n{}  {}NETWORK TRAFFIC {} Not all the hosts are reachable{}\n\n".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_white']))
        exit(1)
    
    def generate_all_traffic(self):
        print("\n\n{}  {}NETWORK TRAFFIC {} Starting Network Traffic between all hosts{}\n\n".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_white']))

        for traffic in self.traffic:
            if traffic['type'] == 'ARP':
                self._generate_traffic(traffic['src_host'],traffic['dst_host'],traffic['type'],0,0,0)
            else:
                self._generate_traffic(traffic['src_host'],traffic['dst_host'],traffic['type'],traffic['data_size'],traffic['src_port'],traffic['dst_port'])

        print("\n\n{}  {}NETWORK TRAFFIC {} Network Traffic between all hosts completed{}\n\n".format(costants['ping_emote'], costants['ansi_green'],costants['ansi_white'],costants['ansi_white']))

    def _generate_traffic(self,host_src,host_dst,traffic_type,data_size,src_port,dst_port):
        print("{}  {}Traffic {} Generating Traffic from {} to {}{}".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],host_src,host_dst,costants['ansi_white']))

        try:
            host_src = self.network_controller.get(host_src)
        except Exception as e:
            print_error("Impossible to get the host {}".format(host_src))
            print_error("Exiting...")
            exit(1)

        try:
            host_dst = self.network_controller.get(host_dst)
        except Exception as e:
            print_error("Impossible to get the host {}".format(host_dst))
            print_error("Exiting...")
            exit(1)

        if traffic_type == 'TCP':
            #h2 should be listen on port dst_port
            host_dst.cmd("iperf3 -s -p {} &".format(dst_port))
            #h1 should send data to h2 sending data_size bytes
            data = bytes_to_kilobytes(int(data_size))
            output = host_src.cmd("iperf3 -c {} -p {} -n {} -B {} --cport {} &".format(host_dst.IP(),dst_port,data,host_src.IP(),src_port))
            print(output)
        elif traffic_type == 'UDP':
            #h2 should be listen on port dst_port
            host_dst.cmd("iperf3 -s -p {} -u &".format(dst_port))
            #h1 should send data to h2 sending data_size bytes
            data = bytes_to_kilobytes(int(data_size))
            host_src.cmd("iperf3 -c {} -p {} -n {} -u -B {} --cport {} &".format(host_dst.IP(),dst_port,data,host_src.IP(),src_port))
        else:
            #TODO dealing with data_size
            host_src.cmd("arping -c 1 {}".format(host_dst.IP()))

        print("{}  {}Traffic {} Traffic generated from {} to {}{}".format(costants['ping_emote'], costants['ansi_green'],costants['ansi_white'],host_src,host_dst,costants['ansi_white']))
    
    def load_json(self, path):
        json_file = open(path,'r')
        json_data = json.load(json_file)
        json_file.close()

        #validate json
        if 'traffic' not in json_data or list(json_data.keys()) != ['traffic']:
            print_error("Invalid JSON file: 'traffic' key not found or extra keys found")
            raise Exception('Invalid JSON file')
        
        for traffic in json_data['traffic']:    #check if all keys are valid
            keys = traffic.keys()
            for key in keys:
                if key not in ['type', 'src_host', 'dst_host', 'src_port', 'dst_port', 'data_size']:
                    print_error("Invalid JSON file: invalid key found: {} should not be here".format(key))
                    raise Exception('Invalid JSON file')
                
                if traffic['type'] not in ['TCP','UDP','ARP']:
                    print_error("Invalid JSON file: invalid traffic type: {}".format(traffic['type']))
                    raise Exception('Invalid JSON file')
                
                if traffic['src_host'] not in self.topology.hosts():
                    print_error("Invalid JSON file: invalid source host: {}".format(traffic['src_host']))
                    raise Exception('Invalid JSON file')
                
                if traffic['dst_host'] not in self.topology.hosts():
                    print_error("Invalid JSON file: invalid destination host: {}".format(traffic['dst_host']))
                    raise Exception('Invalid JSON file')
                
                if traffic['type'] == 'ARP':
                    if 'src_port' in traffic or 'dst_port' in traffic:
                        print_error("Invalid JSON file: ARP traffic should not have port numbers")
                        raise Exception('Invalid JSON file')

                #check that data size is a positive integer
                if int(traffic['data_size']) <= 0:
                    print_error("Invalid JSON file: invalid data_size: {}".format(traffic['data_size']))
                    raise Exception('Invalid JSON file')
        
        self.traffic = json_data['traffic']