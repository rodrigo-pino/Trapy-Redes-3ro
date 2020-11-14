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

def accept(conn: Conn):
    return conn.accept()

def dial(address: str):
    conn = Conn()
    conn.socket.bind(("10.0.0.2",6))
    if conn.connect(address) == 1:
        return conn
    return None

def send(conn:Conn, data:bytes) -> int:
    return conn.send(data)

def recv(conn:Conn, length:int) -> Tuple[int, bytes]:
    result = conn.recv(length)
    return len(result), result

def close(conn: Conn):
    conn.close()

# todo: En caso de recibir un paqete final mas del que nos interesa, botarlo
# todo: No enviar mas paquetes de los que puede el reciever. Annadirlo en los header
# todo: implementar flow control
