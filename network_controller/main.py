from network_topology import NetworkTopology
from mininet.net import Mininet
from mininet.log import setLogLevel


def main():
    #Create a network topology object
    topology = NetworkTopology('../config/switches.json')
    
    #Create a Mininet object
    net = Mininet(topology,controller=None,autoSetMacs=True,autoStaticArp=False)


if __name__ == "__main__":
    setLogLevel('debug')
    main()