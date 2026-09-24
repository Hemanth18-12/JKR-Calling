import sys
from fakeredis import TcpFakeServer

def main():
    port = 16379
    print(f"Starting local Redis server on 127.0.0.1:{port}...", flush=True)
    server = TcpFakeServer(("127.0.0.1", port))
    server.serve_forever()

if __name__ == "__main__":
    main()
