from logging import debug, log
import socket
from socket import socketpair
import threading
import time
from collections import deque
from math import ceil
from random import randint
from typing import Set, Tuple
import logging

from utils import (calculate_checksum, from_bytes_to_address,
                   from_bytes_to_flags, link_data, obtain_chunk, parse_address,
                   parse_flags, set_log_level, unify_byte_list, get_source_ip)


class ConnException(Exception):
    pass

class Conn:
    def __init__(self, sock = None, max_segment_size:int = 1000, loglevel:str = "critical") -> None:
        if sock == None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        
        self.socket:socket.socket = sock
        self.server:bool = False
        self.client:bool = False
        self.bound_conns:list = []

        self.secnum:int = randint(0, 100)
        self.acknum:int = 0
        self.i_secnum:int = self.secnum
        self.i_acknum:int = 0
        
        self.timeout:int = 1
        self.est_rtt:int = 1
        self.dev_rtt:int = 0

        self.source_hostport:Tuple[str,int] = self.socket.getsockname()
        self.dest_hostport:Tuple[str,int] = ("",0)

        self.flags = {"cwr":False, "ece":False, "urg":False, "ack":False, "las":False, "rst":False, "syn":False, "fin":False}
        self.lock = threading.Lock()

        self.initialize_send_variables()
        self.initialize_recv_variables()

        level = set_log_level(loglevel)
        logging.basicConfig(format="%(levelname)s:%(message)s", level=level)

    
    def listen(self, max_conn):
        assert self.client == False, "Error! Clients cannot listen for connections."
        assert self.server == False, "Error! Servers can only listen once."
        self.server = True
        self.bound_conns = [None for _ in range(max_conn)]
    
    def accept(self):
        assert self.client == False, "Error! Clients cannot accept connections."
        conn = self.start_child()
        conn.server = True

        for i in range(len(self.bound_conns)):
            connection = self.bound_conns[i]
            if connection == None or connection.socket == None:
                self.bound_conns[i] = conn
                break
        else:
            logging.error("Maximum number of concurrent connections already reached.")
            return
                
        
        while True:
            syn_segment:int = conn.recv_connect(1)
            if syn_segment == 1:
                break
            logging.info("Error while recieving SYN segment, retrying.")
        
        while True:
            conn.send_connect(2)
            conn.socket.settimeout(conn.timeout)
            try:
                conn.secnum += 1
                ack_segment = conn.recv_connect(3)
                if ack_segment == 3:
                    break
                conn.secnum -= 1
            except socket.timeout:
                conn.secnum -= 1
                conn.timeout *= 2
                logging.error("Timeout ocurred while waiting for ACK segment, retrying.")
                logging.debug("Timeout updated to %s",str(conn.timeout))
        
        if ack_segment != 3:
            print(f"Failed to connect with {conn.dest_hostport}. Aborting")
            return None
        
        conn.socket.settimeout(None)
        return conn
    
    def connect(self, address:str):
        assert self.server == False, "Error! Server cannot be client."
        self.client = True
        self.dest_hostport = parse_address(address)
        ip_addr = get_source_ip("10.0.0.0")
        self.socket.bind((ip_addr, 0))
        count = 1
        while True:
            self.send_connect(1)
            self.socket.settimeout(self.timeout)
            try:
                self.secnum += 1
                synack_segment = self.recv_connect(2)
                if synack_segment == 2:
                    break
                self.secnum -= 1
                logging.info("Error while recieving SYNACK segment, retrying.")
            except socket.timeout:
                self.secnum -= 1
                if count < 32:
                    count *= 2
                self.timeout *= 2
                logging.error("Timeout ocurred while waiting for ACK segment, retrying.")
                logging.debug("Timeout updated to %s",str(self.timeout))

        for _ in range(count):
            self.send_connect(3)
        self.secnum += 1

        self.socket.settimeout(None)
        self.i_secnum = self.secnum
        self.i_acknum = self.acknum
        return 1
    
    def send_connect(self, step:int):
        logging.debug(">>>>SEND STEP: %s", step)
        if step == 1 and self.client:
            flags = "syn = 1"
        elif step == 2 and self.server:
            flags = "syn = 1 ack = 1"
        elif step == 3 and self.client:
            flags = "ack = 1"
        else:
            logging.error("Unexpected exception while sending connection segment.(%s)", step)
            return -1
        logging.debug("self.secnum: %s   self.acknum: %s", self.secnum, self.acknum)
        connect = self.make_packet(b"", flags)
        self.socket.sendto(connect, self.dest_hostport)
        self.unacknowledge.appendleft((connect, self.secnum, (time.time(), self.timeout)))
        return step

    def recv_connect(self, step:int):
        logging.debug("<<<<RECV STEP: %s", step)
        packet = self.socket.recv(40)
        try:
            packet = self.decode_packet(packet)
        except ConnException:
            return -1
        
        _, source, dest, secnum, acknum, flags, _ = packet
        if dest != self.socket.getsockname():
            logging.warning(f"Wrong Address, infromation was sent to {dest} instead of {self.socket.getsockname()}.")
            return self.recv_connect(step)
        if source != self.dest_hostport:
            if self.server and step == 1:
                self.dest_hostport = source
            elif self.client and step == 2 and source[0] == self.dest_hostport[0]:
                self.dest_hostport = source
            else:
                logging.warning(f"Wrong Address, infromation arrived from {source} instead of {self.dest_hostport}.")
                return self.recv_connect(step)
        
        if step == 1 and self.server and "syn" in flags:
            self.acknum = secnum + 1
            return step
        
        if ((step == 2 and self.client and "syn" in flags and "ack" in flags) or (step == 3 and self.server and "ack" in flags)) and self.secnum == acknum:
            self.acknum = secnum + 1 
            _, _, (send_time, _) = self.unacknowledge.pop()
            self.update_timeout(send_time)
            return step
        
        logging.error("Unexpected exception while recieving connection segment.(%s)", step)
        return -1

    def send_control(self, flags:str):
        logging.debug("Sent Control with ack: %s and flags: %s", self.acknum, flags)
        on_flags, off_flags = parse_flags(flags)
        if not "ack" in on_flags and not self.flags["ack"]:
            on_flags.add("ack")
        control = self.make_packet(b"", (on_flags, off_flags))
        self.socket.sendto(control, self.dest_hostport)
        return 1

    def send(self, data:bytes, flags:str="") -> int:
        logging.info("PREPARING TO SEND")
        logging.debug("self.secnum: %s self.acknum: %s", self.secnum, self.acknum)
        self.initialize_send_variables()
        t_control = threading.Thread(target=self.recv_control, daemon=True)
        on_flags, off_flags = parse_flags(flags)
        self.sending = True
        t_control.start()
        while self.total_ack < len(data) and self.sending:
            logging.debug("Max bytes aloud to send: %s", self.aloud_to_send)
            local_timeout = time.time() + 10 + self.timeout
            chunk, self.total_sent = obtain_chunk(data, min(self.max_segment, self.aloud_to_send), self.total_sent)
            if self.total_sent == len(data):
                logging.debug("Sending Final Package")
                on_flags.add("fin")
            packet = self.make_packet(chunk,(on_flags, off_flags))
            logging.debug("Sending size %s",len(chunk))
            self.secnum += len(chunk)
            self.socket.sendto(packet, self.dest_hostport)
            self.lock.acquire()
            self.unacknowledge.appendleft((packet, self.secnum, (time.time(), self.timeout)))
            self.lock.release()
            logging.debug("len(unack) >= cong_window: %s total_sent = len(data): %s", len(self.unacknowledge) >= self.cong_window, self.total_sent == len(data))
            while (len(self.unacknowledge) >= self.cong_window or self.total_sent == len(data)) and self.sending:
                if local_timeout - time.time() < 0:
                    logging.error("Timeout ocurred while sending. Stopped sending data.")
                    self.sending = False
                    self.secnum = self.last_ack_sec if self.last_ack_sec != -1 else self.secnum
                    logging.debug("self.secnum: %s",self.secnum)
                    return self.total_ack
                if self.total_ack >= len(data):
                    break
                self.resend()
        logging.debug("self.total_ack: %s len(data): %s self.sending: %s", self.total_ack, len(data), self.sending)
        self.secnum = self.last_ack_sec if self.last_ack_sec != -1 else self.secnum
        self.sending = False
        return self.total_ack

    def resend(self):
        logging.debug("Re-sending data, unacknowledge packets = %s",len(self.unacknowledge))
        aux_list = deque()
        self.lock.acquire()
        for j in range(len(self.unacknowledge)):
            i = len(self.unacknowledge) - (j + 1)
            packet, expected_ack, (send_time, limit_time) = self.unacknowledge[i]
            if time.time() > send_time + limit_time:
                self.congestion_control(timeout=True)
                self.socket.sendto(packet, self.dest_hostport)
                send_time = time.time()
                limit_time *= 2
            aux_list.appendleft((packet, expected_ack, (send_time, limit_time)))
        self.lock.release()
        self.unacknowledge = aux_list

    def recv_control(self):
        while self.sending:
            packet = self.socket.recv(self.max_transm)
            if not self.sending:
                return
            try:
                packet = self.decode_packet(packet)
            except ConnException:
                logging.info("Problem ocurred while decoding package.")
                logging.debug("Packet:",packet)
                continue
            data, source, dest, secnum, acknum, flags, recv_window = packet
            if dest != self.socket.getsockname() or source != self.dest_hostport:
                logging.info("Recieved package from a different connection.")
                logging.debug("This process sends to %s and has address %s.", self.dest_hostport, self.socket.getsockname())
                logging.debug("But it recieved a package from  %s that was sent to %s.", source, dest)
                continue
            if len(data) > 0:
                logging.debug("Recieving data while sending. Data secnum: %s self.acknum: %s.", secnum, self.acknum)
                if secnum > self.acknum:
                    logging.debug(f"Recieving datal len({len(data)}),{data} doing nothing")
                else:
                    logging.debug(f"Recieving Old Data len({len(data)}),{data} re-sending control")
                    self.send_control("ack = 1")
            
            elif "ack" in flags:
                logging.debug("Recievieng Control data ack=%s, self.secnum=%s and flags=%s",acknum, self.secnum, flags)
                self.lock.acquire()
                self.update_last_acknum(acknum)
                self.aloud_to_send = recv_window
                if "fin" in flags:
                    logging.info("Recieved Termination Control.")
                    self.unacknowledge = deque()
                    self.total_ack = acknum - self.i_secnum
                    self.last_ack_sec = acknum
                    self.sending = False
                    self.lock.release()
                    return
                if acknum > self.last_ack_sec:
                    self.last_ack_sec = acknum
                aux_list = deque()
                for j in range(len(self.unacknowledge)):
                    i = len(self.unacknowledge) - (j + 1)
                    _, expected_ack, (send_time,_) = self.unacknowledge[i]
                    logging.debug("Recieving ACK: %s and was expecting: %s.", acknum, expected_ack)
                    if acknum >= expected_ack:
                        self.total_ack = acknum - self.i_secnum
                        self.update_timeout(send_time)
                    else: aux_list.appendleft(self.unacknowledge[i])
                self.unacknowledge = aux_list
                logging.debug("len(self.unacknowledge): %s", len(self.unacknowledge))
                self.lock.release()

    def recv(self, lenght:int) -> bytes:
        self.sending = False
        logging.info("PREPARING TO RECIEVE")
        logging.debug("self.secnum: %s self.acknum: %s", self.secnum, self.acknum)
        self.initialize_recv_variables()
        end_of_conn = 0
        local_timeout = time.time() + 10 + self.timeout
        max_acknum = self.acknum + lenght
        while self.recv_data_total < lenght:
            self.available_buffer = lenght#lenght - self.recv_data_total if lenght - self.recv_data_total > 0 else 0
            self.socket.settimeout(local_timeout - time.time())
            try:
                packet = self.socket.recv(self.max_transm)
            except socket.timeout:
                logging.error("Timeout Ocurred while waiting for a package. Stopped recieving. Returning recieved data.")
                self.socket.settimeout(None)
                return unify_byte_list(self.recv_data)
            try:
                packet = self.decode_packet(packet)
            except ConnException:
                logging.info("Problem ocurred while decoding package.")
                logging.debug("Packet: %s",packet)
                continue
            data, source, dest, secnum, acknum, flags, _ = packet
            if dest != self.socket.getsockname() or source != self.dest_hostport:
                logging.info("Recieved package from a different connection.")
                logging.debug("This process sends to %s and has address %s.", self.dest_hostport, self.socket.getsockname())
                logging.debug("But it recieved a package from  %s that was sent to %s.", source, dest)
                continue
            logging.debug("Recieved Data")
            if secnum == self.acknum and len(data) > 0:
                local_timeout = time.time() + 10 + self.timeout
                logging.debug("Data saved to buffer")
                self.acknum += len(data)
                self.recv_data_total += len(data)
                self.recv_data.append(data)
                if len(self.ahead_packages):
                    self.acknum = link_data(self.recv_data, self.acknum, self.ahead_packages, max_acknum)
                    self.recv_data_total = self.acknum - self.i_acknum
                self.send_control("ack = 1")
                if end_of_conn == self.acknum:
                    logging.info("After Linking sparse data Fin flag found.")
                    break
            elif secnum > self.acknum and len(data) > 0:
                
                try:
                    self.ahead_packages[secnum]
                    logging.debug("Recieving ahead package already added")
                    local_timeout = time.time() + 7 + self.timeout
                except:
                    logging.debug("Adding data to ahead packages")
                    local_timeout = time.time() + 10 + self.timeout
                    self.ahead_packages[secnum] = data
                    if "fin" in flags:
                        logging.debug("FIN flag found in ahead packages")
                        end_of_conn = secnum + len(data)
                self.send_control("ack = 1")
                continue
            elif secnum < self.acknum and len(data) > 0:
                local_timeout = time.time() + 10 + self.timeout
                logging.debug("Re-Sending ACK due to old package arrival")
                self.send_control("ack = 1")
            
            if "fin" in flags:
                logging.debug("Fin Flags stopping reciever.")
                break

        self.socket.settimeout(None)
        logging.info("Sent Termination Control Message")
        self.send_control("ack = 1 fin = 1")
        result = unify_byte_list(self.recv_data)
        return result[0:lenght]

    def close(self):
        logging.debug("Closing socket")
        self.socket.close()
        self.socket = None

    def increase_sending_rate(self):
        if self.slow_start or (self.threshold != -1 and self.cong_window < int(self.threshold)):
            self.cong_window *= 2
        elif self.cong_avoid:
            self.cong_window += 1
        logging.info(">>>>Increasing sending rate>>>>")
        logging.debug("Congestion Control Mechanism: ss(%s) avoidance(%s) Congetion Window Size: %s Threshold: %s", self.slow_start, self.cong_avoid, self.cong_window, self.threshold)

    def congestion_control(self, timeout=False, triple_ack = False):
        logging.info("<<<<Congestion Control<<<<")
        logging.debug("Timeout Ocurred: %s 3ple ACK recieved: %s",timeout, triple_ack)
        logging.debug("ss(%s) avoidance(%s) window size: %s threshold: %s", self.slow_start, self.cong_avoid, self.cong_window, self.threshold)
        if self.slow_start or (self.threshold != -1 and self.cong_window <= int(self.threshold)):
            self.threshold = ceil(self.cong_window/2)
            self.cong_window = 1
            self.slow_start = False
            self.cong_avoid = True
        elif self.cong_avoid:
            if timeout:
                self.threshold = ceil(self.cong_window/2)
                self.cong_window = 1
                self.cong_avoid = False
                self.slow_start = True
            elif triple_ack:
                self.threshold = ceil(self.cong_window/2)
                self.cong_window = int(self.cong_window/2) + 3
                #self.cong_avoid = False
                #self.fast_recovery = True
        logging.debug("Update: ss(%s) avoidance(%s) window size: %s threshold: %s", self.slow_start, self.cong_avoid, self.cong_window, self.threshold)

    def update_last_acknum(self,new_acknum:int):
        old_acknum, times = self.recv_last_acknum
        if old_acknum != new_acknum:
            self.increase_sending_rate()
            self.recv_last_acknum = (new_acknum, 0)
            return
        times += 1
        if times >= 3:
            self.congestion_control(triple_ack=True)

    def update_timeout(self, out_rtt):
        sam_in_rtt = time.time() - out_rtt
        self.est_rtt = 0.875*self.est_rtt + 0.125*sam_in_rtt
        self.dev_rtt = 0.75*self.dev_rtt + 0.25*abs(sam_in_rtt - self.est_rtt)
        self.timeout =  self.est_rtt + 4*self.dev_rtt
        logging.debug("Timeout Updated to %s", self.timeout)

    def set_flags(self, flags, temp:bool = False) -> bytes:
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
        source_port = self.socket.getsockname()[1].to_bytes(2, "big")
        dest_port = self.dest_hostport[1].to_bytes(2, "big")

        sequence_num = self.secnum.to_bytes(4, "big") 
        acknowledge_num = self.acknum.to_bytes(4, "big")

        flags = self.set_flags(tcp_flags, temp=True)
        recv_window  = b"\x00\x00" #self.available_buffer.to_bytes(2, "big")

        data_offset_reserved = b"\x50"
        urgent_pointer =b"\x00\x00" 
        
        tcp_header = source_port + dest_port + sequence_num + acknowledge_num + data_offset_reserved + flags + recv_window
        checksum = calculate_checksum(tcp_header + urgent_pointer)
        
        tcp_header = tcp_header + checksum + urgent_pointer
        
        return tcp_header + data

    def decode_packet(self, packet:bytes) -> Tuple[bytes, Tuple[str,int], Tuple[str,int], int, int, Set[str], int]:
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
        offset_reserved, flags, recv_window = tcp_header[12], tcp_header[13], tcp_header[14:16]
        checksum, urgentpointer = tcp_header[16:18], tcp_header[18:20]

        source_port = int.from_bytes(source_port, "big")
        dest_port = int.from_bytes(dest_port, "big")
        secnumber = int.from_bytes(secnumber, "big")
        acknumber = int.from_bytes(acknumber, "big")
        recv_window= 2**32-1#int.from_bytes(recv_window, "big")
        flags = from_bytes_to_flags(flags)

        return data, (source_addr, source_port), (dest_addr, dest_port), secnumber, acknumber, flags , recv_window

    def initialize_send_variables(self):
        self.i_secnum = self.secnum
        self.i_acknum = self.acknum
        self.sending = False
        self.max_segment:int = 1000
        self.max_transm:int = 40 + self.max_segment
        self.total_sent = 0
        self.total_ack = 0
        self.aloud_to_send = self.max_transm
        self.unacknowledge = deque()
        self.last_ack_sec = -1
        
        self.cong_window:int = 1
        self.threshold:int  = -1
        self.recv_last_acknum = (-1, -1)
        self.slow_start = True
        self.cong_avoid:bool = False
        self.fast_recovery:bool = False
    
    def initialize_recv_variables(self):
        self.i_secnum = self.secnum
        self.i_acknum = self.acknum
        self.recv_window:int = 1
        self.recv_data_total:int = 0
        self.recv_data = []
        self.ahead_packages = dict()
        self.available_buffer:int = 2*32 - 1

    def start_child(self):
        conn = Conn()
        conn.socket.bind((self.socket.getsockname()[0],0))
        conn.server = self.server
        conn.client = self.client
        conn.source_hostport = self.source_hostport
        conn.dest_hostport = self.dest_hostport
        conn.secnum = self.secnum
        conn.acknum = self.acknum
        conn.i_secnum = self.i_secnum
        conn.i_acknum = self.i_acknum
        conn.flags = self.flags
        return conn

