import re
import shlex
import subprocess
import logging
from math import ceil
from typing import Tuple


def parse_address(address:str):
    host, port = address.split(':')

    if host == '':
        host = 'localhost'

    return host, int(port)

def from_address_to_bytes(address) -> bytes:
    if address == "":
        return b"\x00\x00\x00\x00"

    address = address.split('.')
    byte_address = bytes()
    for n in address:
        byte_address += int(n).to_bytes(1,"big")
    return byte_address

def from_bytes_to_address(address:bytes) -> str:
    result = ".".join(str(byte) for byte in address)
    return result

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
    flags = [(128,"cwr"), (64,"ece"), (32,"urg"), (16,"ack"), (8,"las"), (4,"rst"), (2,"syn"), (1,"fin")]
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

def link_data(data:bytes, sparse_data:dict, acknum:int, max_acknum:int) -> Tuple[int, bytes]:
    if acknum >= max_acknum:
        return max_acknum, data
    for secnum in sparse_data:
        if secnum < acknum:
            sparse_data.pop(secnum)
            return link_data(data, sparse_data, acknum, max_acknum)
        elif secnum == acknum:
            value = sparse_data.pop(secnum)
            acknum += len(value)
            data += value
            return link_data(data, sparse_data, acknum, max_acknum)
    return acknum, data

def sum_list(data:list):
    sum = []
    prev = 0
    for chunk in data:
        prev += len(chunk)
        sum.append(prev)
    return sum

def obtain_chunk(data:bytes, window_size:int, index:int):
    result = data[index:index + window_size]
    index = min(index + window_size, len(data))
    return result, index

def unify_byte_list(data:list):
    unify = b""
    for i in data:
        unify += i
    return unify

def get_source_ip(host):
    this = subprocess.check_output(shlex.split(f"ip route get to {host}"))

    temp1 = str(this, "utf8").split("src")
    temp2 = temp1[1].split("uid")
    
    return temp2[0].split()[0]

def get_secuence_num(header:bytes) -> int:
    secnum = header[4:8]
    return int.from_bytes(secnum, "big")

def set_log_level(level:str) -> int:
    level = level.lower()
    levels = {"debug":logging.DEBUG, "info":logging.INFO, "warning":logging.WARNING, "error":logging.ERROR,"critical":logging.CRITICAL}
    try:
        severity = levels[level]
    except KeyError:
        logging.error("Level \'%s\' is unknow, set \'warning\' as default severity level.",level)
        return logging.WARNING
    return severity

