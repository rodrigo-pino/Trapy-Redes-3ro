from trapy import close, recv, dial, send

#host = "127.0.0.1"
host = "10.0.0.1"
port = 6
print("-------------CLIENT--------------")
tests = ["a", "0123456789", "#0123456789ABCDEF","ReallyBigPackage000000001234567890A1234567890B01234567890C01234567890"]
client = dial(host + f":{port}")
if client:
    for val in tests:
        #val = input("Input Data:")
        send(client, bytes(val,"utf8"))
        print("*******Data Sent***********\n", val)
        r = recv(client, 10)
        print("*******Data Recieved*******\n", r)
        print("----------Succeded-----------")
    close(client)
