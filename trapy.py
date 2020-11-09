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
    if not conn.flags["syn"]:
        conn.set_flags("syn = 1")
    syn = conn.recv_connect()
    if isinstance(syn, int) and syn == 0:
        conn.set_flags("syn = 0")
        new_conn = conn.dup()
        new_conn.send_connect("ack = 1 syn = 1")
        return new_conn

def dial(address: str) -> Conn:
    addr = parse_address(address)
    conn = Conn(dest_host_port=addr)
    conn.socket.bind(("10.0.0.2",6))
    conn.set_flags("syn = 1")
    conn.send_connect("")
    synack = conn.recv_connect()
    if isinstance(synack, int) and synack == 1:
        conn.set_flags("syn = 0")
        return conn

def send(conn:Conn, data:bytes) -> int:
    return conn.send(data)

def recv(conn:Conn, length:int):
    result = conn.recv(length)
    conn.reset_recv_values()
    return unify_byte_list(result)

def close(conn: Conn):
    conn.close()

# todo: enviar y recibir paquetes que funcione
# todo: implementar como trabajar con la congestion de paquetes
# todo: establecer varias conexiones a la vez
# todo: si el ack y el sec son muy grandes que sean modulo de 2**n -1
# todo: refactor
