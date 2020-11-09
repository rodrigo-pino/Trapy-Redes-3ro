from trapy import close, recv, dial, send

#host = "127.0.0.1"
host = "10.0.0.1"
port = 6
print("-------------CLIENT--------------")
client = dial(host + f":{port}")
if client:
    while True:
        val = "0123456789l"
        #val = input("Input Data:")
        send(client, bytes(val,"utf8"))
        print("*******Data Sent***********\n", val)
        r = recv(client, 10)
        print("*******Data Recieved*******\n", r)
        print("----------Succeded-----------")
    close(client)