#!/usr/bin/env python3
import socket
import sys
import argparse
from configuration import read_configurations

CONFIGURATION = read_configurations()

def send_cmd(cmd: str, socket_path: str):
    """
    Sends a command to a Unix domain socket server.

    This function creates a Unix domain socket, connects to the server
    specified by the socket_path, and sends the provided command as a
    UTF-8 encoded string.

    Args:
        cmd (str): The command to send to the server.
        socket_path (str): The path to the Unix domain socket.

    Raises:
        FileNotFoundError: If the socket file specified by socket_path does not exist.
        ConnectionRefusedError: If the connection to the server is refused.
        OSError: For other socket-related errors.
    """
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(socket_path)
            client.sendall(cmd.encode())
    except FileNotFoundError:
        print(f"Error: The socket file '{socket_path}' does not exist.", file=sys.stderr)
    except ConnectionRefusedError:
        print(f"Error: Connection to the server at '{socket_path}' was refused.", file=sys.stderr)
    except OSError as e:
        print(f"Socket error: {e}", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(
        description="Send a command to a Unix domain socket server."
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "toggle"],
        nargs="?",
        default="toggle",
        help="The command to send to the server (default: toggle).",
    )
    args = parser.parse_args()

    send_cmd(args.command, CONFIGURATION["socket_path"])

if __name__ == "__main__":
    main()
