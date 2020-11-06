import socket
from random import randint
from socket import INADDR_ANY
from utils import parse_flags, from_address_to_bytes, calculate_checksum, from_bytes_to_flags
from utils import from_bytes_to_address
from typing import Tuple, Set

class Conn:
    def __init__(self, sock=None, dest_host_port=None, window_size=1500) -> None:
        if sock == None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            
        self.socket:socket.socket = sock
        self.secnum:int = randint(0, 100)
        self.acknum:int = 0
        self.window_size:int = window_size
        
        self.source_hostport = self.socket.getsockname()
        self.dest_hostport = dest_host_port

        self.connecting = False
        self.data_transm = False

        self.flags = {"cwr":False, "ece":False, "urg":False, "ack":False, "psh":False, "rst":False, "syn":False, "fin":False}
    
        
    def set_flags(self, flags:str="") -> bytes:
        on_flags, off_flags = parse_flags(flags)
        flags_bytes = {"cwr":128, "ece":64, "urg":32, "ack":16, "psh":8, "rst":4, "syn":2, "fin":1}

        for flag in on_flags:
            self.flags[flag] = True
        for flag in off_flags:
            self.flags[flag] = False
        
        num = 0
        for flag in self.flags:
            num += flags_bytes[flag] if self.flags[flag] else 0
        
        return num.to_bytes(1, "big")

    def make_packet(self, data:bytes=b"", tcp_flags:str="") -> bytes:
        def make_ip_header():
            # IP HEADER STRUCTURE:
            # Version(4), IHL(4), Type of Service(8) | Total Length(16)
            # Identification(16) | Flags(3), Fragment Offset(13)
            # TTL(8), Protocol(8) | Header Checksum(16)
            # Source Address(32)
            # Destination Address(32)

            ipv_ihl = b"\x45"
            type_service = b"\x00"
            total_lenght =  (20 + 20 + len(data)).to_bytes(2, "big")
            identification = b'\x00\x00'
            flags_offset = b'\x00\x00'
            ttl = b'\x40'
            protocol = b'\x06'
            source_address = from_address_to_bytes(self.socket.getsockname()[0])
            dest_address = from_address_to_bytes(self.dest_hostport[0])#(self.socket.getpeername()[0])
            
            ip_header1 = ipv_ihl + type_service + total_lenght + identification + flags_offset + ttl + protocol
            ip_header2 = source_address + dest_address
            checksum = calculate_checksum(ip_header1 + ip_header2)
            
            print("Encoding IP Header")
            #print("IP Calculated Checksum", int.from_bytes(checksum, "big"))
            return ip_header1 + checksum + ip_header2

        def make_tcp_header():
            # TCP HEADER STRUCTURE:
            # Source Port(16) | Destination Port(16)
            # Sequence Number(32)
            # Acknowledgement Number(32)
            # Data Offset(4), Reserved(4), Flags(8) | Window Size(16)
            # Checksum(16) | Urgent Pointer(16)

            source_port = self.socket.getsockname()[1].to_bytes(2, "big")
            dest_port = self.dest_hostport[1].to_bytes(2, "big")#socket.getpeername()[1].to_bytes(2, "big")
            sequence_num = self.secnum.to_bytes(4, "big") 
            acknowledge_num = self.acknum.to_bytes(4, "big")
            data_offset_reserved = b"\x50"
            flags = self.set_flags(tcp_flags)
            window_size  = self.window_size.to_bytes(2, "big")
            urgent_pointer =b"\x00\x00" 
            
            tcp_header = source_port + dest_port + sequence_num + acknowledge_num + data_offset_reserved + flags + window_size
            checksum = calculate_checksum(tcp_header + urgent_pointer)
            print("Encoding TCP Header")
            print("source port:", self.socket.getsockname()[1])
            print("destination port", self.dest_hostport[1])
            #print("TCP Calculated Checksum", int.from_bytes(checksum, "big"))
            print("TCP Flags:",tcp_flags, "Num:", int.from_bytes(flags, "big"))

            return tcp_header + checksum + urgent_pointer

        #ip_header = make_ip_header()
        print("source address:", self.socket.getsockname()[0])
        print("destination address", self.dest_hostport[0])
        tcp_header = make_tcp_header()
        #print("Raw TCP Header:\n",tcp_header)
        #print("Raw Packet:\n",ip_header + tcp_header + data)
        return tcp_header + data

    def decode_packet(self, packet:bytes) -> Tuple[bytes, int, int, Set[str]]:
        #print("Raw Packet:\n",packet)
        def decode_ip_header(ip_header:bytes):
            print("Decoding IP Header")
            ipv_ihl, typeservice, totallength = ip_header[0:1], ip_header[1:2], ip_header[2:4]
            ident, flags_offset = ip_header[4:6], ip_header[6:8]
            ttl, protocol, checksum = ip_header[8], ip_header[9], ip_header[10:12]
            source_addr = ip_header[12:16]
            dest_addr = ip_header[16:20]

            #print("IP Header Checksum:",int.from_bytes(checksum, "big"))
            #print("IP Calculated Checksum:", int.from_bytes(calculate_checksum(ip_header), "big"))
            assert calculate_checksum(ip_header) == b"\x00\x00", "Checksum Error during IP layer demultiplexing."
            dest_addr = from_bytes_to_address(dest_addr)
            source_addr = from_bytes_to_address(source_addr)
            print("Destination Address:", dest_addr)
            print("Source Address:", source_addr)
            return dest_addr, source_addr
        
        def decode_tcp_header(tcp_header:bytes):
            print("Decoding TCP Header:")
            #print("Raw TCP Header:\n", tcp_header)
            sourceport, destport = tcp_header[0:2], tcp_header[2:4]
            secnumber= tcp_header[4:8]
            acknumber = tcp_header[8:12]
            offset_reserved, flags, window_size = tcp_header[12:13], tcp_header[13:14], tcp_header[14:16]
            checksum, urgentpointer = tcp_header[16:18], tcp_header[18:20]
            
            #print("TCP Header Checksum:",int.from_bytes(checksum, "big"))
            #print("TCP Calculated Checksum:", int.from_bytes(calculate_checksum(tcp_header), "big"))
            assert calculate_checksum(tcp_header) == b"\x00\x00", "Checksum Error during TCP layer demultiplexing."

            sourceport = int.from_bytes(sourceport, "big")
            destport = int.from_bytes(destport, "big")
            print("Destination Port:", destport)
            print("Source Port:", sourceport)
            secnumber = int.from_bytes(secnumber, "big")
            acknumber = int.from_bytes(acknumber, "big")
            flags2= from_bytes_to_flags(flags)
            print("TCP Header On Flags: [", ", ".join([i for i in flags2]), "]", "Num:",int.from_bytes(flags, "big"))
            return secnumber, acknumber, flags2, sourceport

        
        ip_header = packet[0:20]
        tcp_header = packet[20:40]
        data = packet[40:]

        dest_addr, source_addr = decode_ip_header(ip_header)
        secnumber, acknumber, flags, source_port = decode_tcp_header(tcp_header)
        return data, secnumber, acknumber, flags, source_addr, source_port

    def dup(self):
        conn = Conn(self.socket.dup())
        conn.source_hostport = self.source_hostport
        conn.dest_hostport = self.dest_hostport
        conn.secnum = self.secnum
        conn.acknum = self.acknum
        conn.connecting = self.connecting
        conn.data_transm = self.data_transm
        conn.flags = self.flags
        return conn

class ConnException(Exception):
    pass