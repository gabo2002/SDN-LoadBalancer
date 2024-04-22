# SDN Final Project A.A 2023/2024 @Polimi

This project implements a load balancing system based on Software Defined Networking (SDN) using the Ryu framework. The primary goal of this SDN controller is to fairly distribute network traffic among multiple available paths, reducing congestion and enhancing overall network performance.

Our aim is to provide an efficient and flexible load balancing solution, allowing traffic to be routed through least-cost alternative paths for each new connection. Additionally, our controller implements a controller-less routing approach to improve scalability and reduce load on the SDN server.

The cost of each path is calculated in 3 different ways:
- **Hop Count**: The cost of each link is determined by the number of hops required to reach the destination.
- **OSPF variation**: The cost of each link is determined by the Open Shortest Path First (OSPF) routing protocol, by using data throughput of a link as a metric.
- **Dynamic Bandwidth**: The cost of each link is determined by the available bandwidth of the link at the time of a new connection request.

In case of multiple paths with the same cost, the controller will randomly select one of the available paths to distribute the traffic load.

## Installation

To run this project, you need to have the following software installed on your machine:

- [Mininet](http://mininet.org/download/) -> This project has been tested with Mininet version _2.3.1b4_
- [Ryu](https://ryu-sdn.org/) -> We recommend using Ryu version 4.34
- [Python 3.8](https://www.python.org/downloads/) -> There is a known issue with future versions of Python, so we recommend using Python 3.8
- [iPerf3](https://iperf.fr/iperf-download.php)
- [NetworkX](https://networkx.org/)

After installing the required software, you can clone this repository using the following command:

```bash
git clone https://github.com/gabo2002/SoftwareDefinedNetworking-2024.git
```

## Usage

To run the project, you need to follow these steps:

1. Start a Mininet network topology by running the following command:
    ```bash
    sudo python3 network_controller/main.py
    ```

    In this step, you can choose the network topology you want by just changing the `topology_folder_location` field located in `config/constants.json` file. You can even create new topologies from scratch by following the format described [here](#topology).
    In case you want to use a default topology created using mininet command line, you can run the following command:

    ```bash
    sudo mn --arp --mac --topo=<topology_name> --controller=remote,ip=<controller_ip>,port=<config/costants.json['controller_port']>
    ```

2. Start the Ryu controller by running the following command:

    ```bash
    ryu-manager --observe-links --ofp-tcp-listen-port <config/costants.json['controller_port']>  <your_path_to_repo>/ryu_controller/main.py <your_path_to_repo>/ryu_controller/stats_monitor.py
    ```

    Where `<your_path_to_repo>` is the path to the cloned repository on your machine.

3. (Optional) By default, ryu controller does not provide any graphical interface to monitor the network. To monitor the network, you can add the following parameter to the command above:

    ```bash
    <flowmanager_installation_path>/flowmanager/flowmanager.py
    ```
    Where flowmanager.py is another RyuApp that can be found [here](https://github.com/martimy/flowmanager).


By default, this project uses the `Hop Count` cost calculation method. To change the cost calculation method, you can modify the `config/constants.json` file.

After running the commands above, the network controller will also start testing the network by sending ping requests and iperf3 traffic between hosts. You can monitor the network traffic and the load balancing process by checking the stdout of the Ryu controller. As for the network topology, you can configure the network traffic by modifying the `traffic.json` file. More information about how to configure the network traffic can be found [here](#traffic).

## Config

### Constants
The cost calculation method, network controller location and topology config file can be configured by modifying the `config/constants.json` file. The format of the file is as follows:

```json
{
    "debug": true,
    "cost_protocol": "DYNAMIC_BANDWIDTH",
    "topology_folder_location": "ring_topology",
    "controller_port": 6969,
    "controller_host": "localhost",
    "OSPF_reference_bandwidth": 100000000
}
```
Available cost calculation methods are:
- **HOP**
- **OSPF**
- **DYNAMIC_BANDWIDTH**

Debug mode can be enabled by setting the `debug` parameter to `true`. In debug mode, the controller will print additional information about the network traffic and the load balancing process. 
**Important**: Enabling debug mode will change the behavior of the controller while dealing with **OSPF**/**DYNAMIC_BANDWIDTH** cost calculation methods. The controller will take bandwidth measurements from json configuration file instead of the actual bandwidth of the link. This is done due to the bug in Mininet that does not allow to get the actual bandwidth of the link. More information about this bug can be found [here](https://ryu-devel.narkive.com/6cQZgNAi/curr-speed-and-max-speed-isnt-correct). Disabling debug mode will allow the controller to get the actual bandwidth of the link by using OpenFlow protocol.

### Topology
Network topology can be configured by modifying existing topology files in the `config` folder or by creating a new topology folder. Every topology folder should contain two files: `switches.json` and `traffic.json`. The first file contains the list of switches and links between them, while the second file contains the list of traffic flows between hosts.
The format of the `switches.json` file is as follows:
```json
{
    "switches": [
        {
            "id": "S1",
            "hosts" : [
                {
                    "hostid" : "H1",
                    "ip" : "192.168.0.1",
                    "bw" : 1
                }
            ],
            "connected_switches": [
                {
                    "switchid": "S2",
                    "bw": 1
                },
                {
                    "switchid": "S3",
                    "bw": 1
                }
            ]
        },
        {
            "id": "S2",
            "hosts" : [
                {
                    "hostid" : "H2",
                    "ip" : "192.168.0.2",
                    "bw" : 1
                }
            ],
            "connected_switches": [
                {
                    "switchid": "S3",
                    "bw": 1
                }
            ]
        },
        {
            "id": "s3",
            "hosts" : [
                {
                    "hostid" : "H3",
                    "ip" : "192.168.0.3",
                    "bw": 1000
                }
            ],
            "connected_switches": []
        }
    ]
}
```

That creates a network topology as follows:

```
H1 -- S1 -- S2 -- H2
       |    |
       S3 --+
       |
       H3

```

As you can see, a link should be defined only once in the `connected_switches` list. The link is bidirectional, so you don't need to define it twice. The `bw` parameter is the available bandwidth of the link in _Mbps_, and it is used in the `Dynamic Bandwidth` and `OSPF variation` cost calculation method.
In case of invalid topology, the controller will raise an error and stop the network. More information about the configuration error will be printed in the stdout of the controller to help you fix the issue.

### Traffic
Network traffic can be configured by modifying the `traffic.json` file located in the `config/<topology_name>/` folder.
 This file contains the list of traffic flows between hosts. The format of the file is as follows:

```json
{
    "traffic": [
        {
            "type" : "TCP",
            "src_host":"H1",
            "dst_host":"H13",
            "src_port" : 8000,
            "dst_port" : 8080,
            "data_size": 10000
        },
        {
            "type" : "UDP",
            "src_host":"H2",
            "dst_host":"H12",
            "src_port" : 8000,
            "dst_port" : 8080,
            "data_size": 10000
        },
        {
            "type" : "ARP",
            "src_host":"H2",
            "dst_host":"H12",
            "data_size": 200
        },
    ]
}
```

The file contains a list of traffic flows, where each flow is defined by the following parameters: 
- `type`: The type of the traffic flow. It can be either `TCP`, `UDP`, or `ARP`.
- `src_host`: The source host of the traffic flow.
- `dst_host`: The destination host of the traffic flow.
- `src_port`: The source port of the traffic flow. This parameter is only used for `TCP` and `UDP` traffic.
- `dst_port`: The destination port of the traffic flow. This parameter is only used for `TCP` and `UDP` traffic.
- `data_size`: The size of the data to be sent in the traffic flow in _bytes_.

**Note:** in case of `ARP` traffic, the `src_port` and `dst_port` parameters are not used. The `data_size` parameter is used to determine the number of ARP packets to be sent.

In case of invalid traffic configuration, the controller will raise an error and stop the network. More information about the configuration error will be printed in the stdout of the controller to help you fix the issue.

## License
You can find the license for this project [here](LICENSE).
This project is licensed under the MIT License.