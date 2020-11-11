import signal
import socket
import threading
import time
from collections import deque
from math import ceil
from random import randint
from socket import timeout
from threading import Timer
from typing import Set, Tuple

from utils import (calculate_checksum, chunk_bytes, from_address_to_bytes,
                   from_bytes_to_address, from_bytes_to_flags, link_data,
                   parse_flags, sum_list, obtain_chunk, unify_byte_list)


class ConnException(Exception):
    pass

class Conn:
    def __init__(self, sock=None, dest_host_port=None, mss=2) -> None:
        if sock == None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        self.socket:socket.socket = sock
        
        
        self.secnum:int = randint(0, 100)
        self.acknum:int = 0
        self.i_secnum:int = self.secnum
        self.i_acknum:int = 0
        
        self.window_size:int = 30
        self.mtu:int =  40 + self.window_size        
        self.timeout:int = 1
        self.est_rtt:int = 1
        self.dev_rtt:int = 0

        self.source_hostport = self.socket.getsockname()
        self.dest_hostport = dest_host_port

        self.flags = {"cwr":False, "ece":False, "urg":False, "ack":False, "las":False, "rst":False, "syn":False, "fin":False}

        self.unacknowledge = deque()
        self.total_sent = 0
        self.send_index = 0
        self.max_send = 5
        self.sending = False
        self.stop_sending_secnum:int = 0

        self.recv_data_total = 0
        self.recv_data = []
        self.recv_index = -1
        self.ahead_packages = dict()

        self.lock = threading.Lock()

    def send_connect(self, flags:str):
        on_flags, off_flags = parse_flags(flags)
        if not "syn" in on_flags and not self.flags["syn"]:
            return -1
        
        connect = self.make_packet(b"", (on_flags, off_flags))
        self.secnum += 1
        self.i_secnum = self.secnum
        self.socket.sendto(connect, self.dest_hostport)
        self.unacknowledge.appendleft((connect, self.secnum, (time.time(), self.timeout)))
        return 1
    
    def send_control(self, flags:str):
        on_flags, off_flags = parse_flags(flags)
        if not "ack" in on_flags and not self.flags["ack"]:
            return -1
        control = self.make_packet(b"", (on_flags, off_flags))
        self.socket.sendto(control, self.dest_hostport)
        return 1

    def send(self, data:bytes, flags:str=""):
        print("PREPARING TO SEND")
        on_flags, off_flags = parse_flags(flags)
        self.total_sent = 0
        self.total_ack = 0
        self.unacknowledge = deque()
        self.stop_sending_secnum = 0

        self.sending = True
        t_control = threading.Thread(target=self.recv_control, daemon=True)
        t_control.start()
        while self.total_ack < len(data) and self.sending:
            chunk, self.total_sent = obtain_chunk(data, self.window_size, self.total_sent)
            if self.total_sent == len(data):
                on_flags.add("fin")
            packet = self.make_packet(chunk,(on_flags, off_flags))
            self.secnum += len(chunk)
            self.socket.sendto(packet, self.dest_hostport)
            self.unacknowledge.appendleft((packet, self.secnum, (time.time(), self.timeout)))
            while (len(self.unacknowledge) == self.max_send or self.total_sent == len(data)) and self.sending:
                self.resend()
        
        if not self.sending:
            self.secnum = self.stop_sending_secnum

        self.sending = False

    def resend(self):
        aux_list = deque()
        self.lock.acquire()
        for j in range(len(self.unacknowledge)):
            i = len(self.unacknowledge) - (j + 1)
            packet, expected_ack, (send_time, limit_time) = self.unacknowledge[i]
            if time.time() > send_time + limit_time:
                self.socket.sendto(packet, self.dest_hostport)
                send_time = time.time()
                limit_time *= 2
            aux_list.appendleft((packet, expected_ack, (send_time, limit_time)))
        self.lock.release()
        self.unacknowledge = aux_list

    def recv_control(self):
        while self.sending:
            packet = self.socket.recv(40)
            try:
                packet = self.decode_packet(packet)
            except ConnException:
                print("Bad Package", packet)
                continue
            data, source, dest, secnum, acknum, flags = packet
            if dest != self.socket.getsockname() or source != self.dest_hostport:
                print("wrong destination")
                continue
            if "ack" in flags:
                print("Ack Recieved", acknum, "total sent", self.total_sent, "total acknowldgd", self.total_ack)
                self.lock.acquire()
                if "fin" in flags:
                    print("Recieved Termination",self.unacknowledge)
                    self.unacknowledge = deque()
                    self.stop_sending_secnum = acknum
                    self.sending = False
                    self.lock.release()
                    return
                aux_list = deque()
                for j in range(len(self.unacknowledge)):
                    i = len(self.unacknowledge) - (j + 1)
                    _, expected_ack, (send_time,_) = self.unacknowledge[i]
                    print("acknum",acknum, "expected_ack",expected_ack)
                    if acknum >= expected_ack:
                        self.total_ack = acknum - self.i_secnum;print("Total Ack updated",self.total_ack)
                        self.update_timeout(send_time)
                    else: aux_list.appendleft(self.unacknowledge[i])
                self.unacknowledge = aux_list
                self.lock.release()

    def recv_connect(self):
        if not self.flags["syn"]:
            return -1

        packet = self.socket.recv(self.mtu)
        try:
            packet = self.decode_packet(packet)
        except ConnException:
            print("Bad Package", packet)
            return self.recv_connect()
        data, source, dest, secnum, acknum, flags = packet
        
        if dest != self.socket.getsockname() or source != self.dest_hostport:
            if self.dest_hostport == None:
                    self.dest_hostport = source
            else:
                return self.recv_connect()
        if not "syn" in flags:
            return -1
        
        self.acknum = secnum + 1
        self.i_acknum = self.acknum
        
        if "ack" in flags:
            pack, expected_ack, timer = self.unacknowledge.pop()
            self.update_timeout(timer[0])
            return 1
        return 0
        
    def recv(self, lenght:int):
        print("PREPARING TO RECIEVE")
        end_of_conn = 0
        while self.recv_data_total < lenght:
            packet = self.socket.recv(self.mtu)
            try:
                packet = self.decode_packet(packet)
            except ConnException:
                print("Bad Package", packet)
                continue
            data, source, dest, secnum, acknum, flags = packet
            if dest != self.socket.getsockname() or source != self.dest_hostport:
                print("wrong destination")
                continue
            print("recv",data)

            print("recieving secnum",secnum,"self.acknum",self.acknum)
            if secnum == self.acknum and len(data) > 0:
                print("Saved Data", data)
                self.acknum += len(data)
                self.recv_data_total += len(data)
                self.recv_data.append(data)
                self.recv_index += 1
                if len(self.ahead_packages):
                    self.acknum = link_data(self.recv_data, self.acknum, self.ahead_packages)
                    self.recv_data_total = self.acknum - self.i_acknum
                self.send_control("ack = 1")
                print("Sending Ack", self.acknum)
                if end_of_conn == self.acknum:
                    break
                    return self.recv_data
            elif secnum > self.acknum and len(data) > 0:
                print("Adding to ahead packages")
                try:
                    self.ahead_packages[secnum]
                    continue
                except:
                    self.ahead_packages[secnum] = data
                    if "fin" in flags:
                        end_of_conn = secnum + len(data)
                    continue
            elif secnum < self.acknum and len(data) > 0:
                print("Sending ACK due to old package arrival")
                self.send_control("ack = 1")
            
            if "fin" in flags:
                break
                return self.recv_data
        
        self.send_control("ack = 1 fin = 1")
        print("sent termination")
        self.i_secnum = self.secnum
        return unify_byte_list(self.recv_data)

    def reset_recv_values(self):
        self.recv_data = []
        self.recv_data_total = 0
        self.recv_index = -1
        self.ahead_packages = dict()


    def close(self):
        self.socket.close()
        self.socket = None

    def update_timeout(self, out_rtt):
        sam_in_rtt = time.time() - out_rtt
        self.est_rtt = 0.875*self.est_rtt + 0.125*sam_in_rtt
        self.dev_rtt = 0.75*self.dev_rtt + 0.25*abs(sam_in_rtt - self.est_rtt)
        self.timeout =  self.est_rtt + 4*self.dev_rtt

    def set_flags(self, flags, temp = False) -> bytes:
        if isinstance(flags, str):
            on_flags, off_flags = parse_flags(flags)
        else:
            on_flags, off_flags = flags[0], flags[1]

        flags_bytes = {"cwr":128, "ece":64, "urg":32, "ack":16, "las":8, "rst":4, "syn":2, "fin":1}

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

