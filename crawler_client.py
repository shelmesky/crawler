#!/usr/bin/python
# -- encoding:utf-8 --

import sys
import gevent
from gevent.server import StreamServer
from gevent import httplib
from collections import deque
from gevent.pool import Pool
from gevent.timeout import Timeout


class TCPHandler(object):
    def __init__(self, sock, address):
        self.sock = sock
        self.fileobj = sock.makefile()
        self.address = address
        self.read_buf = deque()
        self.read_buf_size = 0
        self.closed = False
        self.read_body_timeout = 3
        self.request()
    
    def handle_headers(self, headers):
        content_length = headers.get("content-length", 0)
        try:
            content_length = int(content_length)
        except ValueError:
            raise RuntimeError("Invalid content-length.")
        
        if content_length:
            timeout = Timeout.start_new(self.read_body_timeout)
            try:
                try:
                    while True:
                        body = self.buffer_get_size(content_length)
                        if body:
                            gevent.spawn(self.handle_body, body)
                            break
                        
                        if not self.read_to_buffer():
                            self.close()
                            break
                        
                except Timeout:
                    self.clear()
                    print "Read body out of %s seconds." % self.read_body_timeout
            finally:
                timeout.cancel()
    
    def handle_body(self, body):
        print self.headers
        print len(body)
        self.clear()
    
    def parse_headers(self, data):
        try:
            lines = data.splitlines()[:-1]
            headers = {}
            for line in lines:
                key, value = line.split(":")
                headers[key.strip()] = value.strip()
        except ValueError:
            raise RuntimeError("Malformed request line")
        self.headers = headers
        return headers
    
    def request(self):
        while True:
            # 如果检测到client的行结束符
            data = self.buffer_get_delimiter("\r\n\r\n")
            if data:
                #gevent.spawn(self.handle_request, data)
                headers = self.parse_headers(data)
                self.handle_headers(headers)
                
            # 如果读不到数据，说明client已经关闭连接
            # server此时也应该关闭
            if not self.read_to_buffer():
                self.close()
                break

    def read_to_buffer(self):
        # readline()是调用patch之后标准库中的socket模块的_fileobj类的readline
        # 原理是每一次recv(1)，并检测行结束符
        # sock.recv()是调用C的socket模块 是syscall
        #data = self.fileobj.readline()
        if not self.closed:
            data = self.sock.recv(4096)
            if not data:
                return
            self.read_buf.append(data)
            data_length = len(data)
            self.read_buf_size += data_length
            return data_length
    
    def close(self):
        self.sock.close()
        self.closed = True
    
    def clear(self):
        self.read_buf.clear()
        self.read_buf_size = 0
        self.headers = None

    def buffer_get_size(self, size):
        if self.read_buf and self.read_buf_size >= size:
            return self._consume(size)
        return False
    
    def buffer_get_delimiter(self, delimiter):
        if self.read_buf:
            while True:
                loc = self.read_buf[0].find(delimiter)
                if loc != -1:
                    delimiter_len = len(delimiter)
                    return self._consume(loc + delimiter_len)
                if self.buffer_len() == 1:
                    break
                _double_prefix(self.read_buf)
        return False
    
    def buffer_len(self):
        return len(self.read_buf)
    
    def _consume(self, loc):
        if loc == 0:
            return ""
        _merge_prefix(self.read_buf, loc)
        self.read_buf_size -= loc
        return self.read_buf.popleft()
    
    
def _merge_prefix(deque, size):
    if len(deque) == 1 and len(deque[0]) <= size:
        return
    prefix = []
    remaining = size
    while deque and remaining > 0:
        chunk = deque.popleft()
        if len(chunk) > remaining:
            deque.appendleft(chunk[remaining:])
            chunk = chunk[:remaining]
        prefix.append(chunk)
        remaining -= len(chunk)
    if prefix:
        deque.appendleft(type(prefix[0])().join(prefix))
    if not deque:
        deque.appendleft(b"")


def _double_prefix(deque):
    new_len = max(len(deque[0]) * 2,
                  (len(deque[0]) + len(deque[1])))
    _merge_prefix(deque, new_len)


def stream_handler(sock, address):
    handler = TCPHandler(sock, address)


if __name__ == '__main__':
    try:
        port = sys.argv[1]
    except IndexError:
        port = 9001
    print "Server listen on port: ", port
    pool = Pool(1024)
    server = StreamServer(("0.0.0.0", port), stream_handler,
            backlog=128, spawn=pool)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print "Server exit..."
        server.stop()
