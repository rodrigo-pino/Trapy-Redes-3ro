import logging
import socket
from typing import Tuple

from conn import Conn, ConnException
from utils import chunk_bytes, parse_address, unify_byte_list


def listen(address: str, max_connections:int = 1, loglevel:str="warning") -> Conn:
    conn = Conn(loglevel=loglevel)
    addr =  parse_address(address)
    conn.socket.bind(addr)
    conn.listen(max_connections)
    return conn

def accept(conn: Conn, max_segment_size:int = 1000, take_from_buffer:int = 1000):
    return conn.accept(max_segment_size=max_segment_size, take_from_buffer=take_from_buffer)

def dial(address: str, max_segment_size:int = 1000, take_from_buffer:int = 1000, loglevel:str="warning"):
    conn = Conn(max_segment_size=max_segment_size, take_from_buffer=take_from_buffer, loglevel=loglevel)
    if conn.connect(address) == 1:
        return conn
    return None

def send(conn:Conn, data:bytes) -> int:
    return conn.send(data)

def recv(conn:Conn, length:int) -> bytes:
    result = conn.recv(length)
    return result

def close(conn: Conn):
    conn.close()
