#!/usr/bin/python
# -- encoding:utf-8 --
#
# TCP服务器，接受文本协议
# 协议的头部大小为<=4K
# 协议头部的字段由\r\n分割，头部和主体之间由\r\n\r\n分割
# 协议格式模拟了HTTP协议，取消了HTTP的协议头概念，直接将请求主体当作协议头
# HTTP的请求表单内容或者服务器返回内容当作请求主体

import sys
import re
import errno
import gevent
from gevent import monkey
monkey.patch_all() 
import urllib
import httplib
from gevent.server import StreamServer
from collections import deque
from gevent.pool import Pool
from gevent.queue import Queue
from gevent.timeout import Timeout
from cProfile import Profile as profile
from pstats import Stats

DEBUG = False
queue = Queue()
regex_goods = re.compile('result-info">(\d+)')
regex_dealing = re.compile('col\sdealing">\\xd7\\xee\\xbd\\xfc(.*)\\xc8\\xcb\\xb3\\xc9\\xbd\\xbb</div>')


class CrawlerClient(object):
    @staticmethod
    def get_data(hostname, method="GET", url=None, body=None):
        conn = httplib.HTTPConnection(hostname)
        headers = {"User-Agent": "curl 7.22.0"}
        headers = {'Accept-Language':'zh-cn', \
                  'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.22 (KHTML, like Gecko) Ubuntu Chromium/25.0.1364.160 Chrome/25.0.1364.160 Safari/537.22'} 
        conn.request(method, url + "?" + body, headers=headers)
        data = conn.getresponse().read()
        conn.close()
        return data
    
    @staticmethod
    def get_detail_page(keyword):
        hostname, url, body = CrawlerClient.get_query_url(keyword)
        data = CrawlerClient.get_data(hostname, url=url, body=body)
        queue.put_nowait((keyword, data))
    
    @staticmethod
    def decode_print(v):
        try:
            return v.decode('GBK').encode('UTF-8')
        except:
            return v.encode('UTF-8')

    @staticmethod
    def get_query_url(query):
        parms = dict(
            q = query,
            commend = "all",
            ssid = "s5-e",
            search_type = "item",
            sourceId = "tb.index",
            initiative_id = "tbindexz_20130523"
        )
        hostname = "s.taobao.com"
        url = "/search"
        return hostname, url, urllib.urlencode(parms)


def cal_dealing(queue):
    i=1
    final_dealing = {}
    while 1:
        keyword, data = queue.get(True)
        if keyword == None: break
        i+=1
        # dealing_total: 前40个商品的销售总量
        # goods_amount: 每个关键词的宝贝总数
        dealing_total = sum(map(int, regex_dealing.findall(data)))
        goods_amount = regex_goods.findall(data)
        goods_amount = goods_amount[0] if goods_amount else 0
        #final_dealing[str(i) + ":" + urllib.unquote(keyword)] = dealing_total
        final_dealing[urllib.unquote(keyword)] = (dealing_total, goods_amount)
    return final_dealing


class IOStream(object):
    """
    为socket增加read_buffer和处理异常等
    """
    def __init__(self, sock, address):
        self.sock = sock
        self.fileobj = sock.makefile()
        self.address = address
        self.read_buf = deque()
        self.read_buf_size = 0
        self.closed = False
    
    def read_to_buffer(self):
        """
        readline()是调用patch之后标准库中的socket模块的_fileobj类的readline
        原理是每一次recv(1)，并检测行结束符
        sock.recv()是调用C的socket模块 是syscall
        """
        #data = self.fileobj.readline()
        if not self.closed:
            try:
                data = self.sock.recv(4096)
            except Exception, e:
                if e[0] == errno.ECONNRESET:
                    self.close()
                    return
            if not data:
                self.close()
                return
            self.read_buf.append(data)
            data_length = len(data)
            self.read_buf_size += data_length
            return data_length
    
    def write(self, data):
        self.sock.send(data)
    
    def close(self):
        self.sock.close()
        self.closed = True
    
    def buffer_get_size(self, size):
        """
        从缓存读取指定大小的字节
        如果达不到要求，则从socket读取到buffer
        """
        while True:
            if self.read_buf and self.read_buf_size >= size:
                return self._consume(size)
            
            # 如果从socket读取失败，说明连接已关闭
            # 则跳出循环
            if not self.read_to_buffer():
                break
        return False
    
    def buffer_get_delimiter(self, delimiter):
        """
        从缓存读取，并查找第一个分隔符
        如果达不到要求，则从socket读取到buffer
        """
        while True:
            if self.read_buf:
                loc = self.read_buf[0].find(delimiter)
                if loc != -1:
                    delimiter_len = len(delimiter)
                    return self._consume(loc + delimiter_len)
                if self.buffer_len() == 1:
                    break
                _double_prefix(self.read_buf)
                
            # 如果从socket读取失败，说明连接已关闭
            # 则跳出循环
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


class TCPHandler(object):
    """
    处理每个连接的类
    """
    def __init__(self, sock, address, callback=None):
        self.stream = IOStream(sock, address)
        self.timeout = 3
        self.callback = callback
        self.request()
    
    def handle_headers(self, headers):
        """
        处理消息头部
        """
        content_length = headers.get("content-length", 0)
        try:
            content_length = int(content_length)
        except ValueError:
            raise RuntimeError("Invalid content-length.")
        
        # 如果请求包含content-length字段
        # 继续读取后续的body
        if content_length:
            timeout = Timeout.start_new(self.timeout)
            try:
                try:
                    body = self.stream.buffer_get_size(content_length)
                    if body:
                        gevent.spawn(self.handle_body, body)
                except Timeout:
                    self.clear()
                    print "Read body out of %s seconds." % self.timeout
            finally:
                timeout.cancel()
    
    def handle_body(self, body):
        """
        处理消息主体
        """
        response_body = self.callback(body)
        
        response_body = str(response_body).encode('hex')
        response_headers ={}
        body_length = len(response_body)
        response_headers.setdefault("type", "response")
        response_headers.setdefault("content-length", body_length)
        response_headers = self.make_headers(response_headers)
        self.stream.write(response_headers)
        self.stream.write(response_body)
        self.clear()
    
    def parse_headers(self, data):
        """
        解析协议头，返回字典
        """
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
    
    def make_headers(self, dicts):
        """
        将字典变为协议头
        每个字段由\r\n结尾，所有字段最后再加上\r\n
        """
        if not isinstance(dicts, dict):
            raise RuntimeError("Invalid headers.")
        f = lambda d: [str(k) + ": " + str(d[k]) + "\r\n"  for k in d]
        return "".join(f(dicts)) + "\r\n"
    
    def request(self):
        """
        循环处理请求，如果socket关闭，退出循环
        """
        while True:
            if self.stream.closed:
                return
            data = self.stream.buffer_get_delimiter("\r\n\r\n")
            if data:
                #gevent.spawn(self.handle_request, data)
                headers = self.parse_headers(data)
                self.handle_headers(headers)
    
    def clear(self):
        self.headres = None


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


def profile_module(callback, *args, **kwargs):
    p = profile()
    p.snapshot_stats()
    p.enable()
    callback(*args, **kwargs)
    p.disable()
    p.print_stats(2)
    #p.dump_stats("handler.log")


def request_handler(data):
    cal_greenlet = gevent.spawn(cal_dealing, queue)
    f = lambda i,s: [i[x:x+s] for x in xrange(0, len(i), s)]
    split_size = 10
    lists = [CrawlerClient.decode_print(i) for i in eval(data.decode('hex'))]
    splited = f(lists, split_size)
    results = []
    for i in splited:
        pool = Pool(split_size)
        [pool.add(pool.spawn(CrawlerClient.get_detail_page, key)) for key in i]
        pool.join()
    
    queue.put((None, None))
    result = cal_greenlet.get()
    return result


def stream_handler(sock, address):
    if DEBUG:
        profile_module(TCPHandler, sock, address, request_handler)
    else:
        TCPHandler(sock, address, request_handler)


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
