from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls


class RuyTest(app_manager.RyuApp):

    def __init__(self, *args, **kwargs):
        super(RuyTest, self).__init__(*args, **kwargs)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        print("Switch detected")

        #Getting the datapath instance from the switch
        datapath = ev.msg.datapath
        #Getting the OpenFlow protocol instance
        ofproto = datapath.ofproto
        #Getting the OpenFlow protocol parser instance -> packet construction
        parser = datapath.ofproto_parser

        #match all packets
        match = parser.OFPMatch()

        #actions
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]

        #instructions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        #Creating the flow mod message
        mod = parser.OFPFlowMod(datapath=datapath, priority=1, match=match, instructions=inst)

        #sending the flow mod message to the switch
        datapath.send_msg(mod)


if __name__ == '__main__':
    controller = RuyTest()