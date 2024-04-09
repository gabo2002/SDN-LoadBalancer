from utils import costants, print_debug, print_error

class NetworkTraffic:
    def __init__(self, network_controller):
        self.network_controller = network_controller
        self.max_ping = 15
        self.ping_timeout = 0.2


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
    
    def generate_traffic(self,host_src,host_dst):
        print("\n\n{}  {}NETWORK TRAFFIC {} Generating Traffic from {} to {}{}\n\n".format(costants['ping_emote'], costants['ansi_red'],costants['ansi_white'],host_src,host_dst,costants['ansi_white']))

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

        self.network_controller.iperf((host_src,host_dst))
        print("\n\n{}  {}NETWORK TRAFFIC {} Traffic generated from {} to {}{}\n\n".format(costants['ping_emote'], costants['ansi_green'],costants['ansi_white'],host_src,host_dst,costants['ansi_white']))
        return