import sys, getopt
from trapy import listen, accept, send, recv, close
#from socket_trapy import *

host = "10.0.0.1"
#host = "0.0.0.0"
port = 6

print("-------------SERVER---------------")
server = listen(host + f":{port}")
server_1 = accept(server)
c = 0
while server_1 != None and c < 5:
    r = recv(server_1, 20)
    print("*******Data Recieved*******\n", r)
    a = send(server_1, r)
    print("*******Data Sent***********\n", r[0:a])
    print("----------Succeded-----------")
    c += 1
    input()
else:
    close(server_1)
close(server)

