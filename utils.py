from math import ceil

def parse_address(address:str):
    host, port = address.split(':')

    if host == '':
        host = 'localhost'

    return host, int(port)

def address_to_bytes(address) -> bytes:
    address = address.split('.')
    byte_address = bytes()
    for n in address:
        byte_address += int(n).to_bytes(1,"big")
    return byte_address

def chunk_bytes(data:bytes, mtu:int=572):
    data_chunk = []
    n = ceil(len(data)/mtu)
    for i in range(n):
        data_chunk.append(data[i*mtu:(i+1)*mtu])
    
    return data_chunk

def set_flags(select) -> bytes:
    select = select.split(" ")
    flags = {"cwr":128, "ece":64, "urg":32, "ack":16, "psh":8, "rst":4, "syn":2, "fin":1}
    num = 0
    for flag in select:
        num += flags[flag.lower()]
    
    return num.to_bytes(1, "big")

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
header = b"\xc0\xa8\x00\xc7"

#r = calculate_checksum(header, "none")
#print(int.from_bytes(r, "big"))

print(chunk_bytes(header, 5))