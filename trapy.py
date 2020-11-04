import socket
import logging
from typing import Tuple

from utils import chunk_bytes, parse_address

from conn import Conn, ConnException


def listen(address: str) -> Conn:
    print("------------Listen Func--------------")
    conn = Conn()
    host, port = parse_address(address)
    
    conn.socket.bind((host, port))
    conn.dest_hostport = (host, port)
    print(f'Socket binded to {address}') #logging.info(f'Socket binded to {address}')
    #conn.socket.listen(1)
    return conn


def accept(conn: Conn) -> Conn:
    print("--------------Accept Func---------------")
    print("Awaiting connection ...")
    flags = recv(conn, 40)
    print("Incomming connection ...")
    if "syn" in flags:
        new_conn = conn.dup()
        new_conn.connecting = True
        send(new_conn, b"", "syn=1 ack=1")
        new_conn.set_flags("syn=0")
        new_conn.connecting = False
        new_conn.data_transm = True
        print("Incomming connection access granted")
        return new_conn


def dial(address: str) -> Conn:
    print("----------------Dial Func-------------------")
    print("Destination Address:", address)
    conn = Conn()

    host, port = parse_address(address)
    
    conn.socket.connect((host, port))
    conn.dest_hostport = (host, port)
    
    conn.connecting = True
    send(conn, b"", "syn = 1")
    print("Asking for permission to connect ...")
    flags = recv(conn, 40)
    if "syn" in flags and "ack" in flags:
        print("Permission Recieved")
        conn.set_flags("ack=1 syn=0")
        conn.connecting = False
        conn.data_transm = True
        return conn

    #Tree Ways Hand Shake:
    #conn.socket.send(conn.make_packet(tcp_flags="syn = 1"))
    #p = conn.socket.recv()

    #return conn


def send(conn:Conn, data:bytes, tcp_flags="", mtu=572) -> int:
    print("--------------Send Func---------------")
    if conn.connecting:
        print("Connecting")
        header = conn.make_packet(data, tcp_flags)
        conn.socket.sendto(header, conn.dest_hostport)
        print(f"Secnum = {conn.secnum}  Acknum = {conn.acknum}")
        conn.secnum += len(data)
        return conn.secnum
    
    print("Data Transmiting:", data)
    data_chunks = chunk_bytes(data, mtu)
    for i, chunk in enumerate(data_chunks):
        if i == len(data_chunks) - 1:
            tcp_flags += " fin = 1 "
        packet = conn.make_packet(chunk, tcp_flags)
        print("i:", i, f"Sending packet({len(packet)}) from:", conn.socket.getsockname(), "To:", conn.dest_hostport)
        print(f"Secnum = {conn.secnum}  Acknum = {conn.acknum}")
        conn.socket.sendto(packet, conn.dest_hostport)
    
    close(conn)
    return conn.secnum


def recv(conn:Conn, length:int):
    print("----------------Recv Func------------------")
    print("Data Transm", conn.data_transm)
    fin = False
    big_data = b""
    length += 40
    while not fin and len(big_data) < length:
        packet = conn.socket.recv(length)
        data, secnum, acknum, tcp_flags = conn.decode_packet(packet)
        print(f"Recieved packet({len(packet)}):", data)
        print(f"Secmnum = {secnum}  Acknum = {acknum}")
        
        if not conn.connecting and "syn" in tcp_flags:
            if conn.data_transm:
                raise ConnException("Connection Error: Flag \"SYN\" detected while data transmission.")

            conn.acknum = secnum + 1
            #conn.connecting = True
            return tcp_flags

        if conn.connecting and "syn" in tcp_flags and "ack" in tcp_flags:
            conn.acknum = secnum + 1
            #conn.set_flags("syn = 0")
            #conn.connecting = False
            #conn.data_transm = True
            return tcp_flags
        
        if conn.data_transm and len(data) == 0:
            raise ConnException("Connection on the other side broke, maybe")

        if conn.data_transm and "ack" in tcp_flags:
            if secnum == conn.acknum:
                conn.acknum = secnum + len(data) + 1
                big_data += data
            elif secnum > conn.acknum:
                pass

        if conn.data_transm and "fin" in tcp_flags:
            fin = True

    close(conn)
    return big_data

def close(conn: Conn):
    print("---------------Close Func-----------------")
    conn.socket.close()
    conn.socket = None


# todo: three way hand shake agregar paso 3. Pulir bien la implementacion de los 2 primeros pasos. Se realizan en accept y dial
# todo: Checkear que los acknum y los secnum coincidan en el data transfer 
# todo: cuando se hace recv verificar que el ack de el otro host coincida con el send
# todo: cuando se hace send verificar que estamos enviando el paquete correcto en caso de haber habido perdida
# todo: implementar ttl o el tiempo que se espera por un paquete
# todo: ver para que sirve el tamanno de ventana y utilizarlo como corresponde
# todo: poder enviar varios paquetes a la vez dependiendo del ancho de banda
# todo: implementar como trabajar con la congestion de paquetes