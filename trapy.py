import logging
import socket
from typing import Tuple

from conn import Conn, ConnException
from utils import chunk_bytes, parse_address


def listen(address: str) -> Conn:
    conn = Conn()
    addr =  parse_address(address)
    conn.socket.bind(addr)
    return conn

def accept(conn: Conn) -> Conn:
    if not conn.flags["syn"]:
        conn.set_flags("syn = 1")
    syn = conn.recv(0)
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
    synack = conn.recv(0)
    if isinstance(synack, int) and synack == 1:
        conn.set_flags("syn = 0")
        return conn

def send(conn:Conn, data:bytes) -> int:
    return conn.send(data)

def recv(conn:Conn, length:int):
    return conn.recv(length)

def close(conn: Conn):
    conn.close()

# todo: Verificar nuevamente los acknum y los secnum
# todo: ver para que sirve el tamanno de ventana y utilizarlo como corresponde
# todo: implementar ttl o el tiempo que se espera por un paquete
# todo: cuando se hace send verificar que estamos enviando el paquete correcto en caso de haber habido perdida
# todo: poder enviar varios paquetes a la vez dependiendo del ancho de banda (Eso tiene que ver con hiperthreading)
# todo: implementar como trabajar con la congestion de paquetes
# todo: refactor
