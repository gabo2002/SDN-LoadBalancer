from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.topology.api import get_switch, get_link, get_all_host, get_all_switch, get_all_link
from ryu.lib.packet import packet, ethernet, ether_types
from utils import print_debug,print_error
import networkx as nx


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
        #print_debug("Packet in event detected from switch with datapath id: {}".format(ev.msg.datapath.id))
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
            #print_debug("Not an IP packet, ignoring")
            return 

        dst = eth.dst
        src = eth.src

        dst_switch, out_port = self._find_destination_switch(dst)

        if dst_switch is None or out_port is None:
            print_error("Destination switch not found")
            return
        
        if datapath.id == dst_switch:
            output_port = out_port
        else:
            output_port = self.find_next_hop_to_destination(datapath.id,dst_switch)

        actions = [parser.OFPActionOutput(output_port)]
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

    def _find_destination_switch(self,dst):
        for host in get_all_host(self):
            if host.mac == dst:
                return (host.port.dpid,host.port.port_no)
        return (None,None)
    
    def find_next_hop_to_destination(self,source_id,destination_id):
        net = nx.DiGraph()
        for link in get_all_link(self):
            net.add_edge(link.src.dpid, link.dst.dpid, port=link.src.port_no)

        path = nx.shortest_path(
            net,
            source_id,
            destination_id
        )

        first_link = net[ path[0] ][ path[1] ]

        return first_link['port']

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):

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

if __name__ == '__main__':
    controller = RyuController()