from trapy import recv, dial, send

#host = "127.0.0.1"
host = "10.0.0.1"
port = 6
client = dial(host + f":{port}")

r = recv(client, length=80)
print(f"Reciving {r}")