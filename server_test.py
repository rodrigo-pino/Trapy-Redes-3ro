import sys, getopt
from trapy import *

#from mininet.node import CPULimitedHost
#from mininet.net import Mininet
#from mininet.link import TCLink
#from mininet.topo import Topo, SingleSwitchTopo

#class SimpleTreeTopo(Topo):
#        def build(self, hosts, switches):
#            assert hosts > 1, "Topology needs two or more hosts."
#            assert switches >  0, "Topology need one or more switches"
#            switch_1 = self.addSwitch("s1")
#            switch_n = None
#            for s in range(1, switches):
#                switch_n = self.addSwitch('s%s' % (s + 1,))
#
#            for h in range(hosts/2):
#                host_1 = self.addHost('h%s' % (h + 1,), cpu=.5/hosts)
#                self.addLink(host_1, switch_1)
#                #host_n = self.addHost('h%s' % (h + hosts/2 + 1,), cpu=.5/hosts)
#                #self.addLink(host_n, switch_n)
            


#def launch_mininet(arguments):
#    simple_tree = SingleSwitchTopo(2)
#    net = Mininet(topo=simple_tree, host=CPULimitedHost, link=TCLink)
#    net.start()
#    h1, h2 = net.get("h1", "h2")
#    print("h1:",h1,"h2:",h2)
#
#    net.ping([h1, h2])
#
#    net.stop()

#def main(argv):
#    launch_mininet("")

#if __name__ == "__main__":
#    main(sys.argv[1:])

host = "10.0.0.1"
#host = "0.0.0.0"
port = 6

print("-------------SERVER---------------")
while True:
    server = listen(host + f":{port}")

    server_1 = accept(server)
    send(server_1, bytes("hola preciosa", "utf8"), mtu=40)
    print("----------------END-----------------\n")

