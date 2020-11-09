from trapy import close, recv, dial, send

#host = "127.0.0.1"
host = "10.0.0.1"
port = 6
print("-------------CLIENT--------------")
client = dial(host + f":{port}")
if client:
    while True:
        val = "1234"#input("Input Data:")
        send(client, bytes(val,"utf8"))
        print("Data Sent", val)
        r = recv(client, 40)
        print("Data Recieved", r)
        break
    close(client)