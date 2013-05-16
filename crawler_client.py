#!/usr/bin/python
# -- encoding:utf-8 --

import sys
import gevent
from gevent.server import StreamServer


def read_one_request(sock):
    response = []
    while True:
        data = sock.recv()


def stream_handler(sock, addr):
    pass


if __name__ == '__main__':
    try:
        port = sys.argv[1]
    except IndexError:
        port = 9001
    server = StreamServer(("0.0.0.0", port), stream_handler)
    server.serve_forever()
