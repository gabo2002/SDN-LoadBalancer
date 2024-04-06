from network_topology import NetworkTopology
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.clean import Cleanup

def main():
    #Create a network topology object
    topology = NetworkTopology('../config/switches.json')
    
    #Create a Mininet object
    network = Mininet(topology,controller=None,autoSetMacs=True,autoStaticArp=False)


if __name__ == "__main__":
    setLogLevel('info')
    #remove any existing Mininet instances
    Cleanup.cleanup()
    main()