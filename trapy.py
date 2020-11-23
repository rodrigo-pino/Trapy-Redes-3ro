import re
from utils import parse_address
from conn import Conn

def listen(address: str, listen:int=1) -> Conn:
    conn = Conn()
    conn.listen(address, 3)
    return conn

def accept(conn: Conn):
    return conn.accept()

def dial(address: str):
    conn = Conn()
    conn.connect(address)
    if conn.connect:
        return conn
    return None

def send(conn:Conn, data:bytes, count:int = 3) -> int:
    sent = conn.send(data)
    if sent == len(data) or count <= 0:
        return sent
    return sent + send(conn, data[sent:], count - 1)

def recv(conn:Conn, length:int) -> bytes:
    return conn.recv(length)

def close(conn:Conn) -> None:
    print("Closing")
    conn.send_control("fin = 1")
    conn.socket.close()
    conn.socket = None
    conn = None

