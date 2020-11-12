import logging
import socket
from typing import Tuple

from conn import Conn, ConnException
from utils import chunk_bytes, parse_address, unify_byte_list


def listen(address: str) -> Conn:
    conn = Conn()
    addr =  parse_address(address)
    conn.socket.bind(addr)
    return conn

def accept(conn: Conn) -> Conn:
    return conn.accept()

def dial(address: str) -> Conn:
    conn = Conn()
    conn.socket.bind(("10.0.0.2",6))
    conn.connect(address)
    return conn

def send(conn:Conn, data:bytes) -> None:
    return conn.send(data)

def recv(conn:Conn, length:int) -> Tuple[int, bytes]:
    result = conn.recv(length)
    return len(result), result

def close(conn: Conn):
    conn.close()

# todo: Hacer el connect y el accept persistentes, o sea si hay perdida de un mensaje reenviar
# todo: implementar flow control
# todo: Maybe add timeouts to avoid hanging for ever for a transmission
# todo: refactor
# todo: test with unittest
