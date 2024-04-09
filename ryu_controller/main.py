from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.topology.api import get_switch, get_link, get_all_host, get_all_switch, get_all_link
from ryu.lib.packet import packet, ethernet, ether_types
from utils import print_debug,print_error
import networkx as nx


class RuyTest(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(RuyTest, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

        self.wsgi = kwargs.get('wsgi', None)
        self.ws_manager = kwargs.get('ws_manager', None)

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

        #match all packets
        match = parser.OFPMatch()

        #actions -> Send everything to the controller if no other rule is matched
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)   #Send to controller with no buffer
        ]

        #instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        #Creating the flow mod message
        mod = parser.OFPFlowMod(datapath=datapath, priority=0, match=match, instructions=inst)

        #sending the flow mod message to the switch
        datapath.send_msg(mod)

    #Event handler executed when a packet in message is received from a switch
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        print_debug("Packet in event detected from switch with datapath id: {}".format(ev.msg.datapath.id))
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
            print_debug("Not an IP packet, ignoring")
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


if __name__ == '__main__':
    controller = RuyTest()