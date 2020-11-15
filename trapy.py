import logging
import socket
from typing import Tuple

from conn import Conn, ConnException
from utils import chunk_bytes, parse_address, unify_byte_list


def listen(address: str, max_connections:int = 1) -> Conn:
    conn = Conn()
    addr =  parse_address(address)
    conn.socket.bind(addr)
    conn.listen(max_connections)
    return conn

def accept(conn: Conn):
    return conn.accept()

def dial(address: str):
    conn = Conn()
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

# todo: pulir congestion control
# todo: ver si recv_last_acknum y la otra que se parece, pueden unirse
# todo: Ver que voy a hace con el recv window al final
# todo: Manejar varios conexiones a la vez
# todo: Hacer un snapshot con todos los prints, o um modo verbose
# todo: bw en wl cli de mininet que significa
# todo: implementar flow control
