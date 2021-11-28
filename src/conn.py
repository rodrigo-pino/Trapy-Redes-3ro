from collections import deque
import logging
from math import ceil
import socket
import time
from random import randint
from utils import calculate_checksum,  from_bytes_to_address, from_bytes_to_flags, link_data, obtain_chunk, parse_address, parse_flags
from logging import debug, error, info, warning
from threading import Thread, Lock

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.CRITICAL)

class Conn():
    def __init__(self, logger=None) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        self.server:bool = False
        self.client:bool = False
        self.bound_conns:list = []
        self.source_hostport = ("",0)
        self.dest_hostport = ("",0)

        self.secnum:int = randint(0, 100)
        self.acknum:int = 0
        self.i_secnum:int = self.secnum
        self.i_acknum:int = 0
        self.max_segment:int = 1040#max_segment_size
        self.recv_window:int = 1040
        self.dynamic_segment_size:int = self.max_segment

        self.timeout:int = 1
        self.est_rtt:int = 1
        self.dev_rtt:int = 0

        self.flags = {"cwr":False, "ece":False, "urg":False, "ack":False, "las":False, "rst":False, "syn":False, "fin":False}
        self.mutex = Lock()

        self.initialize_send_variables()
        self.initialize_recv_variables()
        self.SEND_TIMEOUT = 30
        self.RECV_TIMEOUT = 30
        

    def listen(self, address:str, conn_number:int):
        assert self.client == False, "Error! Clients cannot listen for connections."
        assert self.server == False, "Error! Servers can only listen once."
        self.server = True
        self.source_hostport = parse_address(address)
        self.bound_conns = [None for _ in range(conn_number - 1)]
    
    def accept(self):
        assert self.client == False, "Error! Clients cannot accept connections."
        assert self.server == True, "Error! Server must listen before accepting connections."
        
        while self.recv_connect(1) != 1:
            info("Error while recieving SYN segment, retrying")
        #print("SYN succesfully recived from", self.dest_hostport)
        conn = Conn()
        conn.server = True
        conn.source_hostport = self.source_hostport
        conn.dest_hostport = self.dest_hostport
        conn.secnum = self.secnum
        conn.acknum = self.acknum

        print("Conn bounds",[i == None or i.socket == None for i in self.bound_conns])
        for i in range(len(self.bound_conns)):
            stored_conn = self.bound_conns[i]
            if stored_conn == None or stored_conn.socket == None:
                self.bound_conns[i] = conn
                break
        else:
            warning("Maximum number of concurrent connections already reached.")
            time.sleep(2)
            return None
        local_timeout = time.time() + 15 + conn.timeout
        while time.time() < local_timeout:
            conn.send_connect(2)
            conn.socket.settimeout(conn.timeout)
            try:
                conn.secnum += 1
                if conn.recv_connect(3) == 3:
                    break
                conn.secnum -= 1
                info("Error while recieving ACK segment, retrying.")
            except socket.timeout:
                conn.secnum -= 1
                conn.timeout *= 2
                info("Timeout while waiting for ACK segment, retrying")
        else:
            error("Timeout ocurred while waiting for ACK, aborting")
            conn.socket.settimeout(None)
            return None
        #print("im herre5")
        conn.socket.settimeout(None)
        info("Three-Way Handshake Completed")
        return conn

    def connect(self, address:str):
        assert self.server == False, "Error! Server cannot be client."
        self.client = True
        self.dest_hostport = parse_address(address)
        total_timeouts = 1
        local_timeout = time.time() + 15 + self.timeout
        while time.time() < local_timeout:
            self.send_connect(1)
            self.socket.settimeout(self.timeout)
            try:
                self.secnum += 1
                if self.recv_connect(2) == 2:
                    break
                self.secnum -= 1
                info("Error while recieving SYNACK segment, retrying")
            except socket.timeout:
                self.secnum -= 1
                total_timeouts *= 2 if total_timeouts < 32 else 1 
                self.timeout*=2
                info("Timeout ocurred while waiting for ACK segment, retrying.")
        else:
            self.socket.settimeout(None)
            return 0
        for _ in range(total_timeouts):
            self.send_connect(3)
        self.secnum += 1

        info("Three-Way Handshake completed, hopefully.")
        self.socket.settimeout(None)
        return 1

    def send_connect(self, step:int):
        if step == 1 and self.client:
            flags = "syn = 1"
        elif step == 2 and self.server:
            flags = "syn = 1 ack = 1"
        elif step == 3 and self.client:
            flags = "ack = 1"
        else:
            return 0
        
        packet = self.pack(b"", flags)
        self.socket.sendto(packet, (self.dest_hostport[0],0))
        self.unacknowledge.appendleft(time.time())
        return step

    def recv_connect(self, step:int):
        packet, addr = self.socket.recvfrom(40)
        try:
            _, source, dest, secnum, acknum, flags, recv_window = self.unpack(packet)
        except AssertionError:
            return 0

        if dest[0] != self.source_hostport[0]:
            if self.client and step == 2 and self.source_hostport == ("",0):
                self.source_hostport = dest
            else:
                info(f"Wrong Address, information was meant to {dest} instead of this({self.source_hostport}).")

        if source[0] != self.dest_hostport[0]:
            if self.server and step == 1:
                self.dest_hostport = source
            elif self.client and step == 2 and source[0] == self.dest_hostport[0]:
                self.dest_hostport = source
            else:
                info(f"Wrong Address, information arrived from {source} instead of {self.dest_hostport}.")
                return self.recv_connect(step)

        self.dynamic_segment_size = min(recv_window, self.dynamic_segment_size)
        if step == 1 and self.server and "syn" in flags:
            self.acknum = secnum + 1
            return step
        
        if ((step == 2 and self.client and "syn" in flags and "ack" in flags) or (step == 3 and self.server and "ack" in flags)) and self.secnum == acknum:
            self.acknum = secnum + 1 
            send_time = self.unacknowledge.pop()
            self.update_timeout(send_time)
            return step
        return 0

    def recv_control(self):
        while self.sending:
            packet, addr = self.socket.recvfrom(65565)
            if not self.sending:
                return
            try:
                data, source, dest, secnum, acknum, flags, recv_window = self.unpack(packet)
            except AssertionError:            
                info("A problem ocurred while unpacking")
                continue
            if dest[0] != self.source_hostport[0] or source[0] != self.dest_hostport[0]:
                info("Recieved a package from a different connection.")
                continue
            if len(data) > 0:
                if secnum <= self.acknum:
                    self.send_control("ack = 1")
            
            #debug("self.secnum %s self.acnum %s",self.secnum, self.acknum)
            #debug("acknum %s self.secnum %s", acknum, secnum)
            if "fin" in flags:
                self.mutex.acquire()
                self.unacknowledge = deque()
                self.total_ack = acknum - self.i_secnum
                self.sending = False
                self.mutex.release()
                return    
            if "ack" in flags:
                #print("im herre control with ack", acknum, "and unacknowlede",len(self.unacknowledge))
                self.dynamic_segment_size = min(self.max_segment, recv_window)
                self.mutex.acquire()
                self.update_last_acknum(acknum)
                #print("Recieved ack", acknum)
                aux = deque()
                for j in range(len(self.unacknowledge)):
                    i = len(self.unacknowledge) - (j + 1)
                    pack, expected_ack,(send_time, _) = self.unacknowledge[i]
                    pack_secnum = int.from_bytes(pack[4:8], "big")
                    #debug("expected ack %s", expected_ack)
                    if acknum >= expected_ack:
                        self.total_ack = acknum - self.i_secnum
                        self.update_timeout(send_time)
                    elif pack_secnum < acknum:
                        pack_size = acknum - pack_secnum
                        self.dynamic_segment_size = min(pack_size, self.dynamic_segment_size)
                        #print("Repacking, dynmaic ss", self.dynamic_segment_size)
                        pack_secnum += pack_size
                        re_pack = self.pack(data=pack[20 + pack_size:], flags=pack[12:13], secnum=pack_secnum)
                        aux.append((re_pack, expected_ack, (time.time(), 0)))
                        self.update_timeout(send_time)
                    else:
                        aux.appendleft(self.unacknowledge[i])
                self.unacknowledge = aux
                self.mutex.release()

    def send(self, data:bytes, flags:str="") -> int:
        self.initialize_send_variables()
        on_flags, off_flags = parse_flags(flags)
        self.sending = True
        total_sent = 0
        t_control = Thread(target=self.recv_control, daemon=True)
        t_control.start()
        while self.total_ack < len(data) and self.sending:
            local_timeout = time.time() + self.SEND_TIMEOUT + self.timeout
            chunk, total_sent = obtain_chunk(data, min(self.dynamic_segment_size, len(data) - total_sent), total_sent)
            #if total_sent == len(data):
                #print("Adding fin to on_flags")
                #on_flags.add("fin")
            packet = self.pack(chunk, (on_flags, off_flags))
            self.socket.sendto(packet, (self.dest_hostport[0], 0))
            self.mutex.acquire()
            self.secnum += len(chunk)
            self.unacknowledge.appendleft((packet, self.secnum, (time.time(), self.timeout)))
            self.mutex.release()

            #print("len(unacknowledge)",len(self.unacknowledge))
            while (len(self.unacknowledge) >= self.cong_window or total_sent == len(data)) and self.sending:
                if local_timeout - time.time() < 0:
                    error("Timeout Error while sending. Stopping.")
                    self.sending = False
                    self.secnum = self.recv_last_acknum[0] if self.recv_last_acknum[0] != -1 else self.secnum
                    return self.total_ack
                if self.total_ack >= len(data):
                    break
                self.resend()
        
        #self.socket.sendto(self.pack(b"", "fin = 1"), (self.dest_hostport[0], 0))
        #print("Total data acknowledged", self.total_ack, "len de data",len(data), "self.sending",self.sending)
        self.secnum = self.recv_last_acknum[0] if self.recv_last_acknum[0] != -1 else self.secnum
        self.sending = False
        return self.total_ack

    def resend(self):
        aux_list = deque()
        self.mutex.acquire()
        total_resent = 0
        for j in range(len(self.unacknowledge)):
            i = len(self.unacknowledge) - (j + 1)
            packet, expected_ack, (send_time, limit_time) = self.unacknowledge[i]
            if time.time() > send_time + limit_time and total_resent <= self.cong_window:
                if limit_time > 0:
                    self.congestion_control(timeout=True)
                total_resent += 1
                self.socket.sendto(packet, (self.dest_hostport[0], 0))
                send_time = time.time()
                limit_time =limit_time*2 if limit_time else self.timeout
            aux_list.appendleft((packet, expected_ack, (send_time, limit_time)))
        self.unacknowledge = aux_list
        self.mutex.release()

    def recv(self, length:int) -> bytes:
        self.initialize_recv_variables()
        self.sending = False
        self.recv_window = min(length, self.recv_window)
        recv_data_total:bytes = b""
        ahead_packages = dict()
        end_of_conn = -1
        max_acknum = self.acknum + length
        local_timeout = time.time() + self.RECV_TIMEOUT + self.timeout
        while len(recv_data_total) < length:
            #debug("len(recv_data_tota) %s",len(recv_data_total))
            now = time.time()
            self.socket.settimeout(local_timeout - time.time())
            try:
                packet, addr = self.socket.recvfrom(40 + self.recv_window)
            except socket.timeout:
                error("Timeout ocrred while waiting for a package. Returning recieved till now")
                self.socket.settimeout(None)
                return recv_data_total
            try:
                data, source, dest, secnum, acknum, flags, _ = self.unpack(packet)
            except AssertionError:
                continue
            
            if dest[0] != self.source_hostport[0] or source[0] != self.dest_hostport[0]:
                info("Wrong Address")
                continue
            
            #debug("self.secnum %s self.acnum %s",self.secnum, self.acknum)
            #debug("acknum %s self.secnum %s", acknum, secnum)
            self.update_timeout(now)
            if secnum == self.acknum and len(data) > 0:
                debug("Im herre saving the data")
                local_timeout = time.time() + self.RECV_TIMEOUT + self.timeout
                self.acknum = min(self.acknum + len(data), max_acknum)
                recv_data_total += data
                if len(ahead_packages):
                    #debug("Linking data")
                    self.acknum, recv_data_total = link_data(recv_data_total, ahead_packages, self.acknum, max_acknum)
                self.send_control("ack = 1")
                if self.acknum == end_of_conn or self.acknum == max_acknum:
                    info("Recieved all possible data.")
                    break
            elif secnum > self.acknum and len(data) > 0:
                debug("Ahead package recieved.")
                try:
                    ahead_packages[secnum]
                except:
                    ahead_packages[secnum] = data
                    if "fin" in flags:
                        #debug("fin in flags found in ahead")
                        end_of_conn = secnum + len(data)
                self.send_control("ack = 1")
                local_timeout = time.time() + self.RECV_TIMEOUT + self.timeout
                continue
            elif len(data) > 0:
                debug("Old package recieved, re-sending ACK")
                local_timeout = time.time() + self.RECV_TIMEOUT + self.timeout
                self.send_control("ack = 1")
            
            if "fin" in flags:
                #print("---------------------FIN FLAG recieved")
                break
        
        #debug("sending final control")
        self.socket.settimeout(None)
        #self.send_control("ack = 1 fin = 1")
        return recv_data_total[0:length]

    def send_control(self, flags:str):
        #debug("Senfind ack %s", self.acknum)
        on_flags, off_flags = parse_flags(flags)
        packet = self.pack(b"", (on_flags, off_flags))
        self.socket.sendto(packet, (self.dest_hostport[0], 0))

    
    def pack(self, data:bytes, flags, secnum = -1) -> bytes:
        secnum = self.secnum if secnum == -1 else secnum

        tcp_header  = self.source_hostport[1].to_bytes(2, "big")
        tcp_header += self.dest_hostport[1].to_bytes(2, "big")
        tcp_header += secnum.to_bytes(4, "big")
        tcp_header += self.acknum.to_bytes(4, "big")
        tcp_header += b"\x50"
        tcp_header += self.set_flags(flags, temp=True)
        tcp_header += self.recv_window.to_bytes(2, "big")#Recieve Window
        tcp_header += calculate_checksum(tcp_header)
        tcp_header += b"\x00\x00"

        return tcp_header + data

    def unpack(self, packet:bytes):
        assert len(packet) >= 40, f"Cant unpack, to small({len(packet)})"
        ip_header = packet[0:20]
        assert calculate_checksum(ip_header) == b"\x00\x00", "IP Header compromised, checksum error."
        source_addr = from_bytes_to_address(ip_header[12:16])
        dest_addr = from_bytes_to_address(ip_header[16:20])

        tcp_header = packet[20:40]
        assert calculate_checksum(tcp_header) == b"\x00\x00", "TCP Header compromised, checksum error."
        source_port = int.from_bytes(tcp_header[0:2], "big")
        dest_port = int.from_bytes(tcp_header[2:4], "big")
        secnumber = int.from_bytes(tcp_header[4:8], "big")
        acknumber = int.from_bytes(tcp_header[8:12], "big")
        flags = from_bytes_to_flags(tcp_header[13])
        recv_window = int.from_bytes(tcp_header[14:16], "big")
        

        data = packet[40:]
        return data, (source_addr, source_port), (dest_addr, dest_port), secnumber, acknumber, flags, recv_window

    def congestion_control(self, timeout=False, triple_ack=False):
        #print("Congestion control")
        if self.slow_start:
            self.threshold = ceil(self.cong_window/2)
            self.cong_window = 1
            self.slow_start = False
            self.cong_avoid = True
        elif self.cong_avoid:
            if timeout:
                self.threshold = ceil(self.cong_window/2)
                self.cong_window = 1
                self.slow_start = True
                self.cong_avoid = False
            elif triple_ack:
                self.threshold = ceil(self.cong_window/2)
                self.cong_window = int(self.cong_window/2) + 3

    def increase_sending_rate(self):
        if self.slow_start or (self.threshold != -1 and self.cong_window < int(self.threshold)):
            self.cong_window *= 2
        elif self.cong_avoid:
            self.cong_window += 1

    def update_last_acknum(self,new_acknum:int):
        old_acknum, times = self.recv_last_acknum
        if old_acknum < new_acknum:
            self.increase_sending_rate()
            self.recv_last_acknum = (new_acknum, 0)
            return
        elif old_acknum > new_acknum:
            return
        times += 1
        self.recv_last_acknum = (old_acknum, times)
        if times >= 3:
            self.congestion_control(triple_ack=True)

    def update_timeout(self, out_rtt):
        sam_in_rtt = time.time() - out_rtt
        self.est_rtt = 0.875*self.est_rtt + 0.125*sam_in_rtt
        self.dev_rtt = 0.75*self.dev_rtt + 0.25*abs(sam_in_rtt - self.est_rtt)
        self.timeout =  self.est_rtt + 4*self.dev_rtt
        #debug("Timeout Updated to %s", self.timeout)

    def initialize_send_variables(self):
        self.i_secnum = self.secnum
        self.total_ack = 0
        self.sending = False
        self.slow_start = True
        self.cong_avoid = False
        self.cong_window = 1
        self.threshold = -1
        self.recv_last_acknum = (-1, -1)

        self.mutex.acquire()
        self.unacknowledge = deque()
        self.mutex.release()
    
    def initialize_recv_variables(self):
        self.i_secnum = self.secnum

    def set_flags(self, flags, temp:bool=False) -> bytes:
        if isinstance(flags, bytes):
            return flags
        if isinstance(flags, str):
            on_flags, off_flags = parse_flags(flags)
        else:
            on_flags, off_flags = flags
        
        flags_bytes = {"cwr":128, "ece":64, "urg":32, "ack":16, "las":8, "rst":4, "syn":2, "fin":1}
        if not temp:
            for flag in on_flags:
                self.flags[flag] = True
            for flag in off_flags:
                self.flags[flag] = False
        
        flag_num = 0
        for flag in self.flags:
            flag_num += flags_bytes[flag] if self.flags[flag] else 0
        
        if temp:
            for flag in off_flags:
                flag_num -= flags_bytes[flag] if self.flags[flag] else 0
            for flag in on_flags:
                flag_num += flags_bytes[flag] if not self.flags[flag] else 0
        
        return flag_num.to_bytes(1, "big")
