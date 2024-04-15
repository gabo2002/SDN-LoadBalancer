from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.topology.api import get_switch, get_link, get_all_host, get_all_switch, get_all_link
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp
from utils import print_debug,print_error,print_path,costants
import networkx as nx
import random


'''
    Standard flow entry table for the switches:

    Match: All packets -> priority 1 (only if no other rule is matched)
    Actions: Send to controller
    -> This is the default rule for all the switches, traffic that is not UDP/TCP will be routed as normal traffic

    Match dst MAC -> priority 5
    Actions: Forward to port
    -> This is the rule for the next packets of a connection, the controller will push a new rule to the switch to route the packets using
       standard switching 
    IMPORTANT: Only non TCP/UDP packets must be forwarded using this rule

    Match: TCP packets -> priority 100
    Actions: Send to controller
    -> This is the rule for New TCP connections, the controller will push a new rule to the switch to route the packets using
       the shortest path according to the cost function
    
    Match: UDP packets -> priority 100
    Actions: Send to controller
    -> This is the rule for New UDP connections, the controller will push a new rule to the switch to route the packets using
       the shortest path according to the cost function

    Match: TCP/UDP Connection -> prority 1000
    Actions: Forward to port using the shortest path
    -> This is the rule for the next packets of a connection, the controller had push a new rule to the switch to route the packets using
       the shortest path according to the cost function
    IMPORTANT: Only TCP/UDP packets must be forwarded using this rule

    This is the basic flow entry table for the switches, the controller will push new rules to the switches to route the packets
'''

class RyuController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(RyuController, self).__init__(*args, **kwargs)
        self.connections = list()
        self.net = None

    #Event handler executed when a switch connects to the controller
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_default_features_handler(self, ev):
        print_debug("Detected switch with datapath id: {}".format(ev.msg.datapath.id))

        #Getting the datapath instance from the switch
        datapath = ev.msg.datapath
        #Getting the OpenFlow protocol instance
        ofproto = datapath.ofproto
        #Getting the OpenFlow protocol parser instance -> packet construction
        parser = datapath.ofproto_parser

        #ADDING DEFAULT FLOW ENTRIES -> EVERYTHING TO CONTROLLER
        #match all packets
        match = parser.OFPMatch()

        #actions -> Send everything to the controller if no other rule is matched
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)   #Send to controller with no buffer
        ]

        #instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        #Creating the flow mod message
        mod = parser.OFPFlowMod(datapath=datapath, priority=1, match=match, instructions=inst)

        #sending the flow mod message to the switch
        datapath.send_msg(mod)

        #ADDING FLOW ENTRIES FOR TCP PACKETS
        #create another flow mod message to send the packets to the controller
        #match only tcp connections
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=6,
        )

        #actions -> Send everything to the controller if no other rule is matched
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)   #Send to controller with no buffer
        ]

        #instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        #Creating the flow mod message
        mod = parser.OFPFlowMod(datapath=datapath, priority=100, match=match, instructions=inst)

        #sending the flow mod message to the switch
        datapath.send_msg(mod)

        #ADDING FLOW ENTRIES FOR UDP PACKETS
        #create another flow mod message to send the packets to the controller
        #match only udp connections
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=17,
        )

        #actions -> Send everything to the controller if no other rule is matched
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)   #Send to controller with no buffer
        ]

        #instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        #Creating the flow mod message
        mod = parser.OFPFlowMod(datapath=datapath, priority=100, match=match, instructions=inst)

        #sending the flow mod message to the switch
        datapath.send_msg(mod)

    #Event handler executed when a packet in message is received from a switch
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        #Getting the packet in message
        msg = ev.msg
        #Getting the datapath instance from the switch
        datapath = msg.datapath
        #Getting the OpenFlow protocol instance
        ofproto = datapath.ofproto
        #Getting the OpenFlow protocol parser instance -> packet construction
        parser = datapath.ofproto_parser
        #Getting the in port from the packet in message
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data) 
        eth = pkt.get_protocol(ethernet.ethernet)

        #Check if the packet is an ethernet packet
        if eth is None:
            print_error("No ethernet packet found")
            return
        
        #check if the packet is an LLDP packet
        if eth.ethertype != ether_types.ETH_TYPE_IP:
            return 
        
        #check if the packet is a TCP or UDP packet
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip = pkt.get_protocol(ipv4.ipv4)
            if ip.proto == 6 or ip.proto == 17:
                self._packet_in_TCP_or_UDP_handler(msg,datapath,parser,ofproto,in_port,eth,ip)
            else:
                self._packet_in_not_TCP_or_UDP_handler(msg,datapath,parser,ofproto,in_port,eth)

    #Event handler executed when a packet in message is received from a switch and the packet is a TCP or UDP packet
    def _packet_in_TCP_or_UDP_handler(self,msg,datapath,parser,ofproto,in_port,eth,ip):
        print("\n{} packet received from switch with datapath id: {}".format("TCP" if ip.proto == 6 else "UDP",datapath.id))

        if self.net is None:
            print_debug("Creating network graph...")
            self.net = self.create_net_graph()
            print_debug("Network graph created")

        #Getting the destination MAC address
        dst = eth.dst

        #getting tcp/udp port
        pkt = packet.Packet(msg.data)
        
        if ip.proto == 6:
            tcp_pkt = pkt.get_protocol(tcp.tcp)
            src_port = tcp_pkt.src_port
            dst_port = tcp_pkt.dst_port
            connection_type = 'TCP'
        elif ip.proto == 17:
            udp_pkt = pkt.get_protocol(udp.udp)
            src_port = udp_pkt.src_port
            dst_port = udp_pkt.dst_port
            connection_type = 'UDP'

        #Finding the switch and port where the destination host is connected to
        dst_switch, out_port = self._find_destination_switch(dst)

        #If the destination switch is not found, ignore the packet
        if dst_switch is None or out_port is None:
            print_error("Destination switch not found, ignoring packet")
            return
        
        #I have to calculate the output port
        if datapath.id == dst_switch:   #if the destination is connected to the switch
            output_port = out_port  #I just need to send the packet to the host
            #Creating the packet out message
            if connection_type == 'TCP':
                match = parser.OFPMatch(
                    eth_type = ether_types.ETH_TYPE_IP,
                    ip_proto = ip.proto,
                    ipv4_src = ip.src,
                    ipv4_dst = ip.dst,
                    tcp_src = src_port,
                    tcp_dst = dst_port
                )
            else:
                match = parser.OFPMatch(
                    eth_type = ether_types.ETH_TYPE_IP,
                    ip_proto = ip.proto,
                    ipv4_src = ip.src,
                    ipv4_dst = ip.dst,
                    udp_src = src_port,
                    udp_dst = dst_port
                )
            actions = [parser.OFPActionOutput(output_port)] #output port
            print("Link from switch {} to final host using port: {}".format(datapath.id,output_port))
            #send the packet to the host
            self.send_odf_flow_mod(datapath,parser,match,actions,1000)
        elif self._path_already_exists(src_port,dst_port,ip.src,ip.dst):
            print("This path has been already calculated! Fetching the path from internal memory...")
            #I have to find the path and forward the packet
            found,reverse,connection = self._find_connection(src_port,dst_port,ip.src,ip.dst,datapath.id,dst_switch)
                
            if not found:
                print_error("Connection not found")
                return

            path = connection['path']
            
            if reverse:
                print("Reverse path")
                src_port = connection['dst_port']
                dst_port = connection['src_port']
                ip.src = connection['dst_ip']
                ip.dst = connection['src_ip']

                #iterate the path in reverse until I find the switch where the packet has to be forwarded
                i = len(path)-1
                found = False
                while i >= 0:
                    if path[i] == datapath.id:
                        found = True
                        break
                    i -= 1

                if not found:
                    print_error("Switch not found in the path")
                    return
                
                port = self.net[ path[i] ][ path[i-1] ]['port']
                print("Link from switch {} to switch {} using port: {}".format(path[i],path[i-1],port))
            else:
                #iterate the path until I find the switch where the packet has to be forwarded
                i = 0
                found = False
                while i < len(path):
                    if path[i] == datapath.id:
                        found = True
                        break
                    i += 1

                if not found:
                    print_error("Switch not found in the path")
                    return

                port = self.net[ path[i] ][ path[i+1] ]['port']
                print("Link from switch {} to switch {} using port: {}".format(path[i],path[i+1],port))

            actions = [parser.OFPActionOutput(port)] #output port

            #match this specific tcp/udp connection
            if ip.proto == 6:
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=6,
                    tcp_src=src_port,
                    tcp_dst=dst_port,
                    ipv4_src=ip.src,
                    ipv4_dst=ip.dst
                )
            elif ip.proto == 17:
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_src=src_port,
                    udp_dst=dst_port,
                    ipv4_src=ip.src,
                    ipv4_dst=ip.dst
                )
            #send the packet to the next switch
            self.send_odf_flow_mod(datapath,parser,match,actions,1000)
        else:
            pathsList = nx.all_shortest_paths(self.net, source=datapath.id, target=dst_switch, weight='weight', method='dijkstra')
            #iterable to list 
            paths = list(pathsList)
            print("{}  {}PATH FINDING {}I have found {} possible paths from {} to {}".format(costants['path_emote'],costants['ansi_green'],costants['ansi_white'],len(paths),datapath.id,dst_switch))
            # get a random pathå
            path = random.choice(paths)
            print("{}  {}PATH FINDING {} I have chosen the path: ".format(costants['path_emote'],costants['ansi_green'],costants['ansi_white']),end='')
            print_path(path,datapath.id,dst_switch)
            #create a new connection
            conn = dict()
            conn['src_port'] = src_port
            conn['dst_port'] = dst_port
            conn['src_ip'] = ip.src
            conn['dst_ip'] = ip.dst
            conn['path'] = path

            #add the new connection to the list
            self.connections.append(conn)

            #push the new rul to the switch to forward the packet to the next switch
            first_link = self.net[ path[0] ][ path[1] ]
            actions = [parser.OFPActionOutput(first_link['port'])] #output port

            #match this specific tcp/udp connection
            if ip.proto == 6:
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=6,
                    tcp_src=src_port,
                    tcp_dst=dst_port,
                    ipv4_src=ip.src,
                    ipv4_dst=ip.dst
                )
            elif ip.proto == 17:
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_src=src_port,
                    udp_dst=dst_port,
                    ipv4_src=ip.src,
                    ipv4_dst=ip.dst
                )
            print("Link from switch {} to host using port: {}".format(path[0],first_link['port']))
            #send the packet to the next switch
            self.send_odf_flow_mod(datapath,parser,match,actions,1000)
        
    #Event handler executed when a packet in message is received from a switch and the packet is a TCP or UDP packet
    def _packet_in_not_TCP_or_UDP_handler(self,msg,datapath,parser,ofproto,in_port,eth):
        dst = eth.dst
        dst_switch, out_port = self._find_destination_switch(dst)

        if dst_switch is None or out_port is None:
            return
        
        if datapath.id == dst_switch:   #if the destination is connected to the switch
            output_port = out_port  #I just need to send the packet to the host
        else:   
            output_port = self._find_next_hop_to_destination(datapath.id,dst_switch) #I need to send the packet to another switch
            if output_port is None:
                return

        actions = [parser.OFPActionOutput(output_port)] #output port

        #Creating the packet out message
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )

        datapath.send_msg(out)

        #adding the flow entry to the next packet
        match = parser.OFPMatch(
            eth_dst=dst
        )

        inst = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=5,
            match=match,
            instructions=inst
        )

        datapath.send_msg(mod)

    #Find the switch and port where the destination host is connected to
    def _find_destination_switch(self,dst): 
        for host in get_all_host(self):
            if host.mac == dst:
                return (host.port.dpid,host.port.port_no)
        return (None,None)
    
    #Find the next hop to the destination switch
    def _find_next_hop_to_destination(self,source_id,destination_id):
        net = nx.DiGraph()
        for link in get_all_link(self):
            net.add_edge(link.src.dpid, link.dst.dpid, port=link.src.port_no)
        try:
            path = nx.shortest_path(
                net,
                source_id,
                destination_id
            )
            first_link = net[ path[0] ][ path[1] ]
            return first_link['port']
        except nx.NetworkXNoPath:
            print_error("No path found from {} to {}".format(source_id,destination_id))
            return None

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        return
        for stat in ev.msg.body:
            print("Port: {}".format(stat.port_no))
            print("Rx Packets: {}".format(stat.rx_packets))
            print("Tx Packets: {}".format(stat.tx_packets))
            print("Rx Bytes: {}".format(stat.rx_bytes))
            print("Tx Bytes: {}".format(stat.tx_bytes))
            print("Rx Errors: {}".format(stat.rx_errors))
            print("Tx Errors: {}".format(stat.tx_errors))
            print("Rx Dropped: {}".format(stat.rx_dropped))
            print("Tx Dropped: {}".format(stat.tx_dropped))
            print("Collisions: {}".format(stat.collisions))
            print("Duration Sec: {}".format(stat.duration_sec))
            print("Duration Nsec: {}".format(stat.duration_nsec))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def stats_speed_reply(self,ev):
        return
        for p in ev.msg.body:
            print("Port: {}".format(p.port_no))
            print("HwAddr: {}".format(p.hw_addr))
            print("Name: {}".format(p.name))
            print("Config: {}".format(p.config))
            print("State: {}".format(p.state))
            print("Curr: {}".format(p.curr))
            print("Advertised: {}".format(p.advertised))
            print("Supported: {}".format(p.supported))
            print("Peer: {}".format(p.peer))
            print("Curr Speed: {}".format(p.curr_speed))
            print("Max Speed: {}".format(p.max_speed))

    #Cost function using hop count
    def cost_function_using_hop_count(self,net,src,dst):
        return 1

    #Cost function using OSPF
    def cost_function_using_OSPF(self,net,src,dst):
        #TODO: implement OSPF cost function
        return 1

    #Cost function using dynamic bandwidth
    def cost_function_using_dynamic_bandwidth(self,src,dst):
        #TODO: implement dynamic bandwidth cost function
        return 1
    
    #Check if the path has been already calculated
    def _path_already_exists(self,src_port,dst_port,src_ip,dst_ip):
        for connection in self.connections:
            if connection['src_port'] == src_port and connection['dst_port'] == dst_port and connection['src_ip'] == src_ip and connection['dst_ip'] == dst_ip:
                return True
            #I should check also the reverse path
            if connection['src_port'] == dst_port and connection['dst_port'] == src_port and connection['src_ip'] == dst_ip and connection['dst_ip'] == src_ip:
                return True

        return False

    def _find_connection(self,src_port,dst_port,src_ip,dst_ip,start_switch,dest_switch):
        found = False
        reverse = False
        connection = None

        for i in range(len(self.connections)):
            connection = self.connections[i]
            if connection['src_port'] == src_port and connection['dst_port'] == dst_port and connection['src_ip'] == src_ip and connection['dst_ip'] == dst_ip:
                print("{}  Path: ".format(costants['path_emote']),end='')
                print_path(connection['path'],start_switch,dest_switch)
                found = True
                break
            #reverse path
            if connection['src_port'] == dst_port and connection['dst_port'] == src_port and connection['src_ip'] == dst_ip and connection['dst_ip'] == src_ip:
                print("{}  Path: ".format(costants['path_emote']),end='')
                print_path(connection['path'],start_switch,dest_switch)
                found = True
                reverse = True
                break
        return (found,reverse,connection)

    #Create the network graph using the network topology
    def create_net_graph(self):
        net = nx.DiGraph()
        for link in get_all_link(self):
            if costants['cost_protocol'] == 'HOP':
                weight = self.cost_function_using_hop_count(net,link.src.dpid,link.dst.dpid)
            elif costants['cost_protocol'] == 'OSPF':
                weight = self.cost_function_using_OSPF(link.src.dpid,link.dst.dpid)
            elif costants['cost_protocol'] == 'DYNAMIC_BANDWIDTH':
                weight = self.cost_function_using_dynamic_bandwidth(link.src.dpid,link.dst.dpid)
            else:
                weight = 1
                print_debug("Cost function not found, using default cost function (hop count)...")
            net.add_edge(link.src.dpid, link.dst.dpid, port=link.src.port_no, weight=weight)
        return net
    
    def send_odf_flow_mod(self,datapath,parser,match,actions,priority):
        print_debug("Sending flow mod to switch with datapath id: {}".format(datapath.id))
        ofproto = datapath.ofproto
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

if __name__ == '__main__':
    controller = RyuController()