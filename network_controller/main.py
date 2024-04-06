from network_topology import NetworkTopology
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.clean import Cleanup
from mininet.node import RemoteController
from mininet.util import dumpNodeConnections
import utils
from utils import costants

def main():
    #Get the path of the switches.json file
    path = utils.get_file_path(__file__, '../config/switches.json')

    #Create a network topology object
    topology = NetworkTopology(path)
    
    #Create a Mininet object
    print("{}  {}NETWORK {}Creating Mininet network{}".format(costants['net_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_white']))
    network = Mininet(topology,controller=None,autoSetMacs=True,autoStaticArp=False)

    #add the controller
    network.addController("LoadBalancerController",ip=costants['controller_host'],port=costants['controller_port'],controller=RemoteController)
    #Start the network
    network.start()
    #Dump the connections
    dumpNodeConnections(network.hosts)
    print("{}  {}NETWORK {}Network started{}".format(costants['net_emote'], costants['ansi_green'],costants['ansi_white'],costants['ansi_white']))


if __name__ == "__main__":
    setLogLevel('info')
    #remove any existing Mininet instances
    print("{}  {}CLEANUP {} Removing any existing Mininet instances{}".format(costants['important_emote'], costants['ansi_red'],costants['ansi_white'],costants['ansi_white']))
    Cleanup.cleanup()
    print("{}  {}CLEANUP {} Mininet instances removed{}".format(costants['important_emote'], costants['ansi_green'],costants['ansi_white'],costants['ansi_white']))

    main()