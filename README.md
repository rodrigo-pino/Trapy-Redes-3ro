# Trapy Protocol

Trapy is school project which intends to implement a protocol which mimic a TCP protocol implementation.

_Tested using mininet_

### Main Features

#### Network Congestion

Trapy protocol has a dynamic window size which adapts to current network congestion. For every message sent, an acknowledgment (A message with flag ACK) is expected. When the acknowledgment messages don't arrive, the socket keeps resending the same info, increasing the time interval between each resent in case message are getting lost due to network congestion. After a prudent amount of time it is assumed the other end is unreachable and the connection is closed. In case there is no network congestion, the socket will increase the number of messages sent trying to use all the available bandwidth. The protocol will prioritize playing nice to avoid network collapse but will take any opportunity to increase its messages.

#### Message Cache

Messages in the network can arrive to an endpoint in a different order than when they were initially shipped. Trapy sockets handle this by having a cache of messages received ahead of time, when the missing part is received, it sorts them and unpack the whole bunch and sends an ACK.

### Implementation

It uses the traditional TCP 40 bytes header which has source and destination address, checksum to avoid corruption in message header and signal flags. The main flags used in Trapy are ACK  along with an _acknumber_ that counts the amount of bytes received till the moment, FIN signals that the messaging socket is going to close it's connection and SYN for initial handshake. 

The process of handshake is accomplished in three steps:

* Client ask for connection, a message with the SYN flag on.
* Server acknowledges, a message with SYN and ACK on.
* Client sends a message (can have data) with ACK on, acknowledging the server acknowledge.

### How to Use

```python
import Trapy

# To start as a server:
# address where it is hosted, and
# max number of connections handled concurrently
# returns a Trapy socket initialized as a server
server_conn = listen(address, max_con)
accept(server_conn)

# To start as a client:
# pass the server address
# returns a Trapy socket initialized as a client
client_conn = dial(address)
if client_conn == None:
    raise Exception("Could not connect")
    
# Sending
# Send the data and sets the maximum number of attemps
# It returns the amount of bytes sent
total_bytes_sent:int = send(client_conn, data_in_bytes, attempts)
    
# Recieving
# sets the max segment size when recievign
# returns the data recieved in bytes
data_recieved:bytes = recv(server_conn, max_data_size)
    
# End connection
close(clinet_conn)
close(server_conn)
```

