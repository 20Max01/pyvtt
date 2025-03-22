#!/usr/bin/env python3
import socket
import sys

SOCKET_PATH = "/tmp/voice.sock"

def send_cmd(cmd):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(SOCKET_PATH)
        client.sendall(cmd.encode())

if __name__ == "__main__":
    # Default: toggle
    cmd = "toggle"
    if len(sys.argv) == 2 and sys.argv[1] in ["start", "stop", "toggle"]:
        cmd = sys.argv[1]
    send_cmd(cmd)
