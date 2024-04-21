from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from utils import print_debug,print_error

class ControllerStatsMonitor(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ControllerStatsMonitor, self).__init__(*args, **kwargs)
        self.datapaths = set()
        self.monitor_thread = hub.spawn(self._monitor)
        self.sleep = 5

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_default_features_handler(self, ev):
        print_debug("Detected switch with datapath id: {}".format(ev.msg.datapath.id))

        #send link discovery request
        self.datapaths.add(ev.msg.datapath)
    
    def request_stats(self, datapath):
        print_debug("Requesting stats from switch with datapath id: {}".format(datapath.id))
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    def request_speed_stats(self, datapath):
        parser = datapath.ofproto_parser

        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)
        
    def _monitor(self):
        try:
            while True:
                for dp in self.datapaths:
                    pass
                    self.request_stats(dp)
                    self.request_speed_stats(dp)
                hub.sleep(self.sleep)
        except Exception as e:
            print_error("Received exception {} in monitor thread".format(str(e)))
            print_error("Exiting...")
            exit(1)
