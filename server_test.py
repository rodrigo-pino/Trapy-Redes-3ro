from trapy import listen, send, recv, accept

#host = "127.0.0.1"
host = "0.0.0.0"
port = 8080

print("-------------SERVER---------------")
while True:
    server = listen(host + f":{port}")

    server_1 = accept(server)
    send(server_1, bytes("hola preciosa", "utf8"), mtu=40)
    print("----------------END-----------------\n")
