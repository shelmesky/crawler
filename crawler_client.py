#!/usr/bin/python
# -- encoding:utf-8 --

import sys
import gevent
from gevent.server import StreamServer


def handle_one_request(data, socket_fileobj):
    fileobj = socket_fileobj
    print data
    fileobj.write(data)
    fileobj.flush()


def stream_handler(sock, addr):
    fileobj = sock.makefile()
    fileobj.write("Welcome to server!\r\n")
    fileobj.flush()
    request = []
    while True:
        data = fileobj.readline()
        if not data: break
        if data.strip().lower() == "quit": break
        request.append(data)
        if "".join(request[-2:]) == "\r\n\r\n":
            gevent.spawn(handle_one_request, "".join(request[:-2]), fileobj)
            request = []


if __name__ == '__main__':
    try:
        port = sys.argv[1]
    except IndexError:
        port = 9001
    print "Server listen on port: ", port
    server = StreamServer(("0.0.0.0", port), stream_handler)
    server.serve_forever()
