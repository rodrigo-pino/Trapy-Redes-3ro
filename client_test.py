from trapy import recv, dial, send

#host = "127.0.0.1"
host = "0.0.0.0"
port = 8080
client = dial(host + f":{port}")

r = recv(client, length=80)
print(f"Reciving {r}")