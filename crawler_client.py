#!/usr/bin/python
# -- encoding:utf-8 --

import sys
import gevent
from gevent.server import StreamServer
from gevent import httplib
from collections import deque


class TCPHandler(object):
    def __init__(self, sock, address):
        self.sock = sock
        self.fileobj = sock.makefile()
        self.address = address
        self.read_buf = []
        self.request()
    
    def handle_one_request(self, data):
        print "".join(data).strip()
    
    def parse_headers(self, data):
        pass
    
    def request(self):
        while True:
            # readline()是调用patch之后标准库中的socket模块的_fileobj类的readline
            # 原理是每一次recv(1)，并检测行结束符
            data = self.sock.recv(4096)
            
            # 因为_fileobj仅仅是将socket接口封装成了类文件接口
            # 并增加了读写缓冲
            # 单并没有对客户端断开做任何检测，是很底层的封装
            # 所以这里需要对读取不到数据的连接做检测
            # 动作为断开连接(因为函数执行完毕，即greelnet执行完毕)
            # python执行GC，greenlet对象被销毁，socket连接断开
            if not data: break
            
            if data.strip().lower() == "quit": break
            
            self.read_buf.append(data)
            
            # 如果检测到client的行结束符
            if "".join(self.read_buf[-2:]) == "\r\n\r\n":
                gevent.spawn(self.handle_one_request, self.read_buf[:-2])
                self.read_buf = []
    
    def _consume(self, deque, size):
        pass


def stream_handler(sock, address):
    handler = TCPHandler(sock, address)


if __name__ == '__main__':
    try:
        port = sys.argv[1]
    except IndexError:
        port = 9001
    print "Server listen on port: ", port
    server = StreamServer(("0.0.0.0", port), stream_handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print "Server exit..."
