from math import ceil
from typing import Optional
import re

def parse_address(address:str):
    host, port = address.split(':')

    if host == '':
        host = 'localhost'

    return host, int(port)

def address_to_bytes(address) -> bytes:
    address = address.split('.')
    byte_address = bytes()
    for n in address:
        byte_address += int(n).to_bytes(1,"big")
    return byte_address

def chunk_bytes(data:bytes, mtu:int=572):
    data_chunk = []
    n = ceil(len(data)/mtu)
    for i in range(n):
        data_chunk.append(data[i*mtu:(i+1)*mtu])
    
    return data_chunk

# flags = "urg=0 ece=1 fin=1 ack=0"
def parse_flags(flags:str):
    on_flags = re.findall(r"[a-z][a-z][a-z][ ]*?=[ ]*?1", flags)
    off_flags = re.findall(r"[a-z][a-z][a-z][ ]*?=[ ]*?0", flags)
    for i in range(len(on_flags)):
        on_flags[i] = on_flags[i][0:3]
    for i in range(len(off_flags)):
        off_flags[i] = off_flags[i][0:3]
    return (on_flags, off_flags)

def from_bytes_to_flags(flags_bytes:bytes):
    flags = [(128,"cwr"), (64,"ece"), (32,"urg"), (16,"ack"), (8,"psh"), (4,"rst"), (2,"syn"), (1,"fin")]
    on_flags = set()
    num = int.from_bytes(flags_bytes, "big")
    for bit, flag in flags:
        if num & bit:
            on_flags.add(flag)
    
    return on_flags

def calculate_checksum(header:bytes) -> bytes:
    checksum = 0
    for i in range(int(len(header)/2)):
        header_16b = header[i*2:(i*2)+2]
        header_num = int.from_bytes(header_16b, "big")
        checksum += header_num
    
    while checksum > (2**16 - 1):
        checksum_bytes = checksum.to_bytes(4, "big")
        carry_bytes, checksum_bytes = checksum_bytes[0:2], checksum_bytes[2:4]
        carry, checksum = int.from_bytes(carry_bytes, "big"), int.from_bytes(checksum_bytes, "big")
        checksum += carry
    
    return (~checksum + 2**16).to_bytes(2, "big")



#a = 3
#b = a.to_bytes(2, "big")
#print("len",len(b))
#c = int.from_bytes(b, "little")
#print(c)
#print(a.to_bytes(2, "big"))
#print(a.to_bytes(2, "little"))

#import socket
#sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#sock.bind(("0.0.0.0", 0))
#print("lonp", sock.getsockname())
#print("ronp", sock.getpeername())

#sock.close()

#a = [3,5,2,1,9,6,7]
#print(a[0:3])


#header = b"\x45\x00\x00\x73\x00\x00\x40\x00\x40\x11\xb8\x61\xc0\xa8\x00\x01"
#header = b"\xc0\xa8\x00\xc7"

#r = calculate_checksum(header, "none")
#print(int.from_bytes(r, "big"))

#print(chunk_bytes(header, 5))

#print(parse_flags("ack    =  1 urg = 0 cki  =      1"))

#a = b"\xff"
#a =  int.from_bytes(a, "big")
#print(a)
#b = 128 & 127
#print(b)

#a = b""
#print(len(a))