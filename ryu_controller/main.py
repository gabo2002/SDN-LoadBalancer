from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.topology.api import get_all_host, get_all_link, get_all_switch
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, arp
from utils import print_debug,print_error,print_path,get_file_path,costants
import networkx as nx
import random
import logging
import time
import json
import traceback


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
        self.switch_stats = dict() #switch ports statistics
        self.nominal_bandwidth = dict() #nominal bandwidth obtained from the switch

        self.timestart = time.time()
        #Logging
        log_file_name = get_file_path(__file__, "../ryu_controller.log")
        root_logger = logging.getLogger()
        root_logger.handlers = []
        debug_level = logging.DEBUG if costants['debug'] == True else logging.INFO
        logging.basicConfig(level=debug_level,filename=log_file_name,filemode='a',format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("RyuController")
        self.logger.setLevel(logging.DEBUG)
        #File handler
        fh = logging.FileHandler(log_file_name)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(fh)
        
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
        
        #check if the packet is an arp packet
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self.proxy_arp_handler(msg,datapath,parser,ofproto,in_port,eth)
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

            #route the packet to the host
            self.send_packet_out(datapath,parser,actions,in_port,msg)

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

            #Creating the packet out message
            self.send_packet_out(datapath,parser,actions,in_port,msg)
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

            #Creating the packet out message
            self.send_packet_out(datapath,parser,actions,in_port,msg)
            
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

    #Event handler executed when a packet in message is received from a switch and the packet is an ARP packet
    def proxy_arp_handler(self,msg,datapath,parser,ofproto,in_port,eth):
        #Getting the packet in message
        pkt = packet.Packet(msg.data)
        #get the arp packet
        arp_pkt = pkt.get_protocol(arp.arp)
        
        #If it's not an ARP request, ignore the packet
        if arp_pkt.opcode != arp.ARP_REQUEST:
            return

        #Getting the destination MAC address
        dst_mac = None

        for host in get_all_host(self):
            if arp_pkt.dst_ip in host.ipv4:
                dst_mac = host.mac
                break

        if dst_mac is None:
            print_debug("Destination MAC address not found for arp request with ip: {}".format(arp_pkt.dst_ip))
            return
        
        #creating a packet out message
        packet_out = packet.Packet()

        eth_out = ethernet.ethernet(
            dst = eth.src,
            src = dst_mac,
            ethertype = ether_types.ETH_TYPE_ARP
        )

        arp_out = arp.arp(
            opcode = arp.ARP_REPLY,
            src_mac = dst_mac,
            src_ip = arp_pkt.dst_ip,
            dst_mac = arp_pkt.src_mac,
            dst_ip = arp_pkt.src_ip
        )

        packet_out.add_protocol(eth_out)
        packet_out.add_protocol(arp_out)
        packet_out.serialize()

        actions = [parser.OFPActionOutput(in_port)] #output port

        #Creating the packet out message
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=packet_out.data
        )
        datapath.send_msg(out)

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
        except nx.NodeNotFound as e:
            print_error("Node not found, maybe the switch is not connected to the network, please check the network topology")
            print_error("Error: {}".format(e))
            return None

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        for stat in ev.msg.body:
            if stat.port_no == 4294967294: #4294967294 is the special port number for the entire switch
                continue
            #I should find the dst switch and port
            found = False
            dst_id = None
            for link in get_all_link(self):
                if link.src.dpid == ev.msg.datapath.id:
                    if link.src.port_no == stat.port_no:
                        found = True
                        dst_id = link.dst.dpid
                        break
            
            if not found: #if the port is not found, the connection is a switch-host connection
                continue

            link = "{}:{}".format(ev.msg.datapath.id,dst_id)
            if link not in self.switch_stats.keys():
                self.switch_stats[link] = list()

            temp = dict()
            temp['rx_bytes'] = stat.rx_bytes
            temp['tx_bytes'] = stat.tx_bytes
            temp['timestamp'] = time.time()

            if len(self.switch_stats[link]) > 0:
                #calculate the bandwidth
                prev = self.switch_stats[link][-1]
                duration = temp['timestamp'] - prev['timestamp']
                if duration == 0:
                    duration = 1
                #bandwidth in bits per second
                temp['bandwidth'] = (temp['rx_bytes'] + temp['tx_bytes'] - prev['rx_bytes'] - prev['tx_bytes']) * 8 / duration

            self.switch_stats[link].append(temp)            
            #remove old data from the list
            if len(self.switch_stats[link]) > 2:
                self.switch_stats[link].pop(0)
            
            # Log the statistics
            self.logger.debug("Switch id: {} Port: {} Rx Packets: {}, Tx Packets: {}, Rx Bytes: {}, Tx Bytes: {}, Rx Errors: {}, Tx Errors: {}, Rx Dropped: {}, Tx Dropped: {}, Collisions: {}, Duration Sec: {}, Duration Nsec: {}".format(
                ev.msg.datapath.id, stat.port_no,stat.rx_packets, stat.tx_packets, stat.rx_bytes, stat.tx_bytes, stat.rx_errors, stat.tx_errors, stat.rx_dropped, stat.tx_dropped, stat.collisions, stat.duration_sec, stat.duration_nsec))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def stats_speed_reply(self,ev):
        for p in ev.msg.body:
            if p.port_no == 4294967294: #4294967294 is the special port number for the entire switch
                continue
            
            link = "{}:{}".format(ev.msg.datapath.id,p.port_no)
            self.nominal_bandwidth[link] = p.curr_speed * 1000 #kbps to bps
            self.logger.debug("Switch id: {} Port: {} HwAddr: {} Name: {} Config: {} State: {} Curr: {} Advertised: {} Supported: {} Peer: {} Curr Speed: {} Max Speed: {}".format(ev.msg.datapath.id,p.port_no,p.hw_addr,p.name,p.config,p.state,p.curr,p.advertised,p.supported,p.peer,p.curr_speed,p.max_speed))

    #Cost function using hop count
    def cost_function_using_hop_count(self,src,dst):
        return 1

    #Cost function using OSPF
    def cost_function_using_OSPF(self,src,dst):
        bandwidth = self._load_nominal_bandwidth()

        link_name = "{}:{}".format(src,dst)
        if link_name not in bandwidth.keys():
            print_debug("Link {} not found in the nominal bandwidth list".format(link_name))
            return costants['OSPF_reference_bandwidth']
        
        cost = float(costants['OSPF_reference_bandwidth']) / float(bandwidth[link_name])
        return cost

    #Cost function using dynamic bandwidth
    def cost_function_using_dynamic_bandwidth(self,src,dst):
        bandwidth = self._load_nominal_bandwidth()

        link_name = "{}:{}".format(src,dst)
        if link_name not in bandwidth.keys():
            print_debug("Link {} not found in the nominal bandwidth list".format(link_name))
            return costants['OSPF_reference_bandwidth']
        
        # cost = OSPF reference bandwidth / actual free bandwidth
        nominal_bandwidth = bandwidth[link_name]
        try:
            current_used_bandwidth = self.switch_stats[link_name][-1]['bandwidth']
        except Exception:
            current_used_bandwidth = 0
        
        available_bandwidth = nominal_bandwidth - current_used_bandwidth
        cost = float(costants['OSPF_reference_bandwidth']) / float(available_bandwidth)
        return cost
    
    #This function return 
    def _load_nominal_bandwidth(self):
        bandwidth = dict()
        if costants['debug']:
            #Load nominal bandwidth from file
            try:
                path = get_file_path(__file__ , "../config/{}/switches.json".format(costants['topology_folder_location']))
                file = open(path,'r')
                json_data = json.load(file)
                file.close()
                for switch in json_data['switches']:
                    switch_id = str(switch['id'])[1:]
                    for connected_switch in switch['connected_switches']:
                        connected_switch_id = str(connected_switch['switchid'])[1:]
                        link_bw_s = int(connected_switch['bw']) #mbps
                        link_bw_b = link_bw_s * 1000000
                        bandwidth["{}:{}".format(switch_id,connected_switch_id)] = link_bw_b
                        bandwidth["{}:{}".format(connected_switch_id,switch_id)] = link_bw_b
            except Exception as e:
                print_error("Received exception {} while loading switches from JSON file".format(str(e)))
                print_error("Traceback: {}".format(traceback.format_exc()))
                exit(1)
        else:
            #Load nominal bandwidth from the network by getting the port description
            for switch in get_all_switch(self):
                for link in get_all_link(self):
                    if link.src.dpid == switch.dp.id:
                        try:
                            link_bw = self.nominal_bandwidth["{}:{}".format(switch.dp.id,link.src.port_no)]    
                            bandwidth["{}:{}".format(link.src.dpid,link.dst.dpid)] = link_bw
                            bandwidth["{}:{}".format(link.dst.dpid,link.src.dpid)] = link_bw
                        except Exception:
                            print("Link {} not found in the nominal bandwidth list, using DEFAULT cost".format("{}:{}".format(switch.dp.id,link.src.port_no)))
                            bandwidth["{}:{}".format(link.src.dpid,link.dst.dpid)] = costants['OSPF_reference_bandwidth']
                            bandwidth["{}:{}".format(link.dst.dpid,link.src.dpid)] = costants['OSPF_reference_bandwidth']
        return bandwidth

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
                weight = self.cost_function_using_hop_count(link.src.dpid,link.dst.dpid)
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
    
    def send_packet_out(self,datapath,parser,actions,in_port,msg):
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data
        )
        datapath.send_msg(out)