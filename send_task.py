#!/usr/bin/env python
# --encoding: utf-8 --

import gevent
from gevent import socket
from collections import deque


class IOStream(object):
    def __init__(self, sock, address=None):
        self.sock = sock
        self.fileobj = sock.makefile()
        self.address = address
        self.read_buf = deque()
        self.read_buf_size = 0
        self.closed = False
    
    def read_to_buffer(self):
        # readline()是调用patch之后标准库中的socket模块的_fileobj类的readline
        # 原理是每一次recv(1)，并检测行结束符
        # sock.recv()是调用C的socket模块 是syscall
        #data = self.fileobj.readline()
        if not self.closed:
            data = self.sock.recv(4096)
            if not data:
                self.close()
                return
            self.read_buf.append(data)
            data_length = len(data)
            self.read_buf_size += data_length
            return data_length
    
    def write(self, data):
        return self.sock.send(data)
    
    def close(self):
        self.sock.close()
        self.closed = True
        self.clear()
    
    def clear(self):
        self.read_buf.clear()
        self.read_buf_size = 0

    def buffer_get_size(self, size):
        while True:
            if self.read_buf and self.read_buf_size >= size:
                return self._consume(size)
            
            if not self.read_to_buffer():
                break
        return False
    
    def buffer_get_delimiter(self, delimiter):
        while True:
            if self.read_buf:
                loc = self.read_buf[0].find(delimiter)
                if loc != -1:
                    delimiter_len = len(delimiter)
                    return self._consume(loc + delimiter_len)
                if self.buffer_len() == 1:
                    break
                _double_prefix(self.read_buf)
                
            if not self.read_to_buffer():
                break
        return False
    
    def buffer_len(self):
        return len(self.read_buf)
    
    def _consume(self, loc):
        if loc == 0:
            return ""
        _merge_prefix(self.read_buf, loc)
        self.read_buf_size -= loc
        return self.read_buf.popleft()


class SendTaskClient(object):
    def __init__(self, host=None, port=9001):
        self.host = host
        self.port = port
        self.connect_timeout = 30
        sock = self.connect(self.host, self.port)
        self.stream = IOStream(sock)
    
    def connect(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.connect_timeout)
        self.sock.connect((self.host, self.port))
        return self.sock
    
    def send_task(self, body):
        body_length = len(body)
        headers = {}
        headers.setdefault("type", "request")
        headers.setdefault("content-length", body_length)
        headers = self.make_headers(headers)
        self.stream.write(headers)
        self.stream.write(body)
    
    def recv_response(self):
        response = self.stream.buffer_get_delimiter("\r\n\r\n")
        response_headers = self.parse_headers(response)
        content_length = response_headers.get("content-length", 0)
        try:
            content_length = int(content_length)
        except ValueError:
            raise RuntimeError("Invalid content-length.")
        if content_length:
            response_body = self.stream.buffer_get_size(content_length)
            if response_body:
                return response_body
    
    def make_headers(self, dicts):
        if not isinstance(dicts, dict):
            raise RuntimeError("Invalid headers.")
        f = lambda d: [str(k) + ": " + str(d[k]) + "\r\n"  for k in d]
        return "".join(f(dicts)) + "\r\n"
    
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


def run_test():
    client = SendTaskClient(host="127.0.0.1")
    client.send_task("test content here")
    body = client.recv_response()
    print body

if __name__ == '__main__':
    workers = [gevent.spawn(run_test) for i in range(1000)]
    gevent.joinall(workers)
    
