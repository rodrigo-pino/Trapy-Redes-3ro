import socket
from sys import setdlopenflags
import threading
from threading import Timer
import time
from collections import deque
from random import randint
from typing import Set, Tuple

from utils import (calculate_checksum, chunk_bytes, from_address_to_bytes,
                   from_bytes_to_address, from_bytes_to_flags, link_data,
                   parse_flags, sum_list)


class ConnException(Exception):
    pass

class Conn:
    def __init__(self, sock=None, dest_host_port=None, window_size=2) -> None:
        if sock == None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            
        self.socket:socket.socket = sock
        
        self.secnum:int = randint(0, 100)
        self.acknum:int = 0
        self.i_secnum:int = self.secnum
        self.i_acknum:int = 0
        
        self.window_size:int = window_size
        self.mtu:int = window_size + 40
        
        self.source_hostport = self.socket.getsockname()
        self.dest_hostport = dest_host_port

        self.flags = {"cwr":False, "ece":False, "urg":False, "ack":False, "psh":False, "rst":False, "syn":False, "fin":False}

        self.send_data = None
        self.acknowledged = None
        self.sum_data = None
        self.resend_list = None
        self.total_sent = 0
        self.send_index = 0
        self.max_send = 3

        self.recv_data = []
        self.recv_data_total = 0
        self.recv_index = -1
        self.ahead_packages = dict()
    
    def send_connect(self, flags:str):
        on_flags, off_flags = parse_flags(flags)
        if not "syn" in on_flags and not self.flags["syn"]:
            return -1

        connect = self.make_packet(b"", (on_flags, off_flags))
        self.secnum += 1
        self.i_secnum = self.secnum
        self.socket.sendto(connect, self.dest_hostport)
        return 1
    
    def send_control(self, flags:str):
        on_flags, off_flags = parse_flags(flags)
        if not "ack" in on_flags and not self.flags["ack"]:
            return -1
        control = self.make_packet(b"", (on_flags, off_flags))
        self.socket.sendto(control, self.dest_hostport)
        return 1

    def send(self, data, flags:str=""):
        on_flags, off_flags = parse_flags(flags)

        self.send_data = chunk_bytes(data, self.window_size) if isinstance(data, bytes) else data
        self.acknowledged = [False for i in range(len(self.send_data))]
        self.sum_data = sum_list(self.send_data)
        self.resend_list =[]
        
        t_control = threading.Thread(target=self.recv_control, daemon=True)
        t_resend = threading.Thread(target=self.resend, daemon=True)
        t_control.start()
        t_resend.start()

        current = 0
        while current < len(self.send_data) :
            if current == len(self.send_data) - 1:
                on_flags.add("fin")
            
            data = self.send_data[current]
            packet = self.make_packet(data, (on_flags, off_flags))
            self.socket.sendto(packet, self.dest_hostport)
            self.secnum += len(data)
            self.resend_list.append((current,packet))
            
            while current == self.send_index + self.max_send:
                pass
            current += 1
        return 1
    
    def resend(self):
        while True:
            time.sleep(0.1)
            for i, packet in self.resend_list:
                if self.acknowledged[i]:
                    self.resend_list.remove((i, packet))
                else:
                    self.socket.sendto(packet, self.dest_hostport)
            
    def recv(self, lenght:int):
        while self.recv_data_total <= lenght:
            packet = self.socket.recv(self.mtu)
            try:
                packet = self.decode_packet(packet)
            except ConnException:
                continue
            
            data, source, dest, secnum, acknum, flags = packet
            
            if dest != self.socket.getsockname() or source != self.dest_hostport:
                if self.dest_hostport == None:
                    self.dest_hostport = source
                else:
                    continue
            
            if self.flags["syn"]:
                if "syn" in flags:
                    self.acknum = secnum + 1
                    self.i_acknum = acknum
                    if "ack" in flags:
                        return 1
                    return 0
                return -1
            
            if "ack" in flags and self.send_data:
                self.total_sent = acknum - self.i_secnum
                for i in range(self.send_index, min(len(self.acknowledged), self.send_index + self.max_send)):
                    if self.total_sent >= self.sum_data[i]:
                        self.acknowledged[i] = True
                        self.send_index += 1
                    else:
                        break
            
            if secnum == self.acknum and len(data) > 0:
                self.acknum += len(data)
                self.recv_data_total += len(data)
                self.recv_data.append(data)
                self.recv_index += 1
                total = link_data(self.recv_data, 0, self.ahead_packages)
                self.acknum += total
                self.recv_data_total += total
                self.send_control("ack = 1")
            elif secnum > self.acknum and len(data) > 0:
                try:
                    self.ahead_packages[secnum]
                    continue
                except:
                    self.ahead_packages[secnum] = data
            elif len(data) > 0:
                continue
                
            if "fin" in flags:
                return self.recv_data
        
        return self.recv_data

    def close(self):
        self.socket.close()
        self.socket = None
    
    def recv_control(self):
        while True:
            self.recv(self.recv_data_total)

    def set_flags(self, flags, temp = False) -> bytes:
        if isinstance(flags, str):
            on_flags, off_flags = parse_flags(flags)
        else:
            on_flags, off_flags = flags[0], flags[1]

        flags_bytes = {"cwr":128, "ece":64, "urg":32, "ack":16, "psh":8, "rst":4, "syn":2, "fin":1}

        if not temp:
            for flag in on_flags:
                self.flags[flag] = True
            for flag in off_flags:
                self.flags[flag] = False
        
        num = 0
        for flag in self.flags:
            num += flags_bytes[flag] if self.flags[flag] else 0
        
        if temp:
            for flag in off_flags:
                num -= flags_bytes[flag] if self.flags[flag] else 0
            for flag in on_flags:
                num += flags_bytes[flag] if not self.flags[flag] else 0
        
        return num.to_bytes(1, "big")

    def make_packet(self, data:bytes, tcp_flags) -> bytes:
        source_port = self.socket.getsockname()[1].to_bytes(2, "big");print(f"Sending self.acknum {self.acknum} self.secnum {self.secnum}")
        dest_port = self.dest_hostport[1].to_bytes(2, "big")

        sequence_num = self.secnum.to_bytes(4, "big") 
        acknowledge_num = self.acknum.to_bytes(4, "big")

        flags = self.set_flags(tcp_flags, temp=True)
        window_size  = self.mtu.to_bytes(2, "big")

        data_offset_reserved = b"\x50"
        urgent_pointer =b"\x00\x00" 
        
        tcp_header = source_port + dest_port + sequence_num + acknowledge_num + data_offset_reserved + flags + window_size
        checksum = calculate_checksum(tcp_header + urgent_pointer)
        
        tcp_header = tcp_header + checksum + urgent_pointer
        
        return tcp_header + data

    def decode_packet(self, packet:bytes) -> Tuple[bytes, int, int, Set[str]]:
        ip_header = packet[0:20]
        tcp_header = packet[20:40]
        data = packet[40:]
        
        checksum = int.from_bytes(calculate_checksum(ip_header), "big")
        if checksum != 0:
            raise ConnException(f"IP Header Compromised. Checksum Error. Expected 0 instead {checksum}")
        checksum = int.from_bytes(calculate_checksum(tcp_header), "big")
        if checksum != 0:
            raise ConnException(f"TCP Header Compromised. Checksum Error. Expected 0 instead {checksum}")

        ipv_ihl, typeservice, totallength = ip_header[0], ip_header[1], ip_header[2:4]
        ident, flags_offset = ip_header[4:6], ip_header[6:8]
        ttl, protocol, checksum = ip_header[8], ip_header[9], ip_header[10:12]
        source_addr = ip_header[12:16]
        dest_addr = ip_header[16:20]
        
        dest_addr = from_bytes_to_address(dest_addr)
        source_addr = from_bytes_to_address(source_addr)
    
        source_port, dest_port = tcp_header[0:2], tcp_header[2:4]
        secnumber= tcp_header[4:8]
        acknumber = tcp_header[8:12]
        offset_reserved, flags, window_size = tcp_header[12], tcp_header[13], tcp_header[14:16]
        checksum, urgentpointer = tcp_header[16:18], tcp_header[18:20]

        source_port = int.from_bytes(source_port, "big")
        dest_port = int.from_bytes(dest_port, "big")
        secnumber = int.from_bytes(secnumber, "big")
        acknumber = int.from_bytes(acknumber, "big")
        window_size = int.from_bytes(window_size, "big")
        flags = from_bytes_to_flags(flags)

        return data, (source_addr, source_port), (dest_addr, dest_port), secnumber, acknumber, flags 

    def dup(self):
        conn = Conn(self.socket.dup())
        conn.source_hostport = self.source_hostport
        conn.dest_hostport = self.dest_hostport
        conn.secnum = self.secnum
        conn.acknum = self.acknum
        conn.i_secnum = self.i_secnum
        conn.i_acknum = self.i_acknum
        conn.flags = self.flags
        return conn

