import enum
from math import ceil, modf
from random import randint, sample
from threading import Thread
from time import sleep
from typing import Optional, Sized
import re

def parse_address(address:str):
    host, port = address.split(':')

    if host == '':
        host = 'localhost'

    return host, int(port)

def from_address_to_bytes(address) -> bytes:
    address = address.split('.')
    byte_address = bytes()
    for n in address:
        byte_address += int(n).to_bytes(1,"big")
    return byte_address

def from_bytes_to_address(address:bytes) -> str:
    #result = ""
    #for byte in address:
    #    result += str(byte) + "."
    result = ".".join(str(byte) for byte in address)
    #print("Address to bytes",result)
    return result#[:len(result)-1]

def chunk_bytes(data:bytes, size:int):
    data_chunk = []
    n = ceil(len(data)/size)
    for i in range(n):
        data_chunk.append(data[i*size:(i+1)*size])
    
    return data_chunk

# flags = "urg=0 ece=1 fin=1 ack=0"
def parse_flags(flags:str):
    on_flags = re.findall(r"[a-z][a-z][a-z][ ]*?=[ ]*?1", flags)
    off_flags = re.findall(r"[a-z][a-z][a-z][ ]*?=[ ]*?0", flags)
    for i in range(len(on_flags)):
        on_flags[i] = on_flags[i][0:3]
    for i in range(len(off_flags)):
        off_flags[i] = off_flags[i][0:3]
    return (set(on_flags), set(off_flags))

def from_bytes_to_flags(flags_bytes):
    flags = [(128,"cwr"), (64,"ece"), (32,"urg"), (16,"ack"), (8,"psh"), (4,"rst"), (2,"syn"), (1,"fin")]
    on_flags = set()
    num = int.from_bytes(flags_bytes, "big") if isinstance(flags_bytes, bytes) else flags_bytes
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

def link_data(data:list, total_data:int, sparse_data:dict) -> int:
    for secnum in sparse_data:
        if secnum < total_data:
            sparse_data.pop(secnum)
        elif secnum == total_data:
            value = sparse_data.pop(secnum)
            total_data += len(value)
            data.append(value)
            return link_data(data, total_data, sparse_data)
    return total_data

def sum_list(data:list):
    sum = []
    prev = 0
    for chunk in data:
        prev += len(chunk)
        sum.append(prev)
    return sum

def handler(signum, frame):
    raise TimeoutError()

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

#aaa = b"hola preciosa"
#print(chunk_bytes(aaa, 2))

#print(parse_flags("ack    =  1 urg = 0 cki  =      1"))

#a = b"\xff"
#a =  int.from_bytes(a, "big")
#print(a)
#b = 128 & 127
#print(b)

#a = b""
#print(len(a))

#a = from_bytes_to_address(b"\xff\xff\xff\xaf")
#print(a)

#a = [1,2,3,"a"]
#for i, j in enumerate(a):
#    print(i,j)

#import time
#from threading import Thread
#def a(b:int, c:int):
    #print("Am here")
    #sleep(3)

#t = Thread(target=a,args=(3,4), daemon=True)

#t.start()
#print("CC")
#t.join()

#while True:
#    if not t.is_alive():
#        t.start()
#    print("And Here")
#    time.sleep(3)

#print("And Here")

#def a():
#    signal.signal(signal.SIGALRM, handler2)
#    signal.alarm(3)
#    try:
#        time.sleep(10)
#        print("zzz")
#    except TimeoutError:
#        print("Awake")
#    print("Hachus")
#    signal.alarm(0)

#a()

#data = []
#total_data = 1034
#sparse_data = {1038:"e", 1040:"f", 1035:"b", 1036:"c", 1042:"g", 1034:"a", 1037:"d"}

#total_data = link_data(data, total_data, sparse_data)
#print(data)
#print(total_data)

#def a():
#    return 1,2,3
#_,_,b=a()
#print(b)

#a = [b"5",b"0",b"1",b"2",b"3",b"4"]
#func = lambda x: randint(0,1)
#a.sort(key=func,)
#print(a)