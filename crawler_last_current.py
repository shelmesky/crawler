#!/usr/bin/python
#--encoding: utf-8--

import time
import re
import gevent
from gevent import monkey
import httplib
import urlparse
from gevent import queue
from gevent.pool import Pool
from pyquery import PyQuery as pq
from prettyprint.prettyprint import pp
import random
import urllib
import multiprocessing
import os

monkey.patch_all()

import sys
reload(sys)
sys.setdefaultencoding('UTF-8')


keywords_map = None
relative_map = None
ip_pool = ["180.153.152.37", "180.153.152.43", "180.153.152.44"]
ip_pool = ["180.153.152.37"]

def get_random_obj(obj):
    return random.choice(obj)


def get_keyword_list_url(keyword):
    parms = dict(
        extras = 1,
        code = "utf-8",
        bucket_id = 14,
        callback = "KISSY.Suggest.callback",
        q = keyword
    )
    hostname = "suggest.taobao.com"
    url = "/sug"
    return hostname, url, urllib.urlencode(parms)

def get_query_url(query):
    parms = dict(
        q = query,
        commend = "all",
        ssid = "s5-e",
        search_type = "item",
        sourceId = "tb.index",
        initiative_id = "tbindexz_20130426"
    )
    hostname = "s.taobao.com"
    url = "/search"
    return hostname, url, urllib.urlencode(parms)


class GetConn(object):
    conn_map = dict()
    
    @staticmethod
    def get_conn(host):
        cls = GetConn
        if host in cls.conn_map:
            conns = ls.conn_map[host]
        else:
            cls.conn_map[host] = list()
            for ip in ip_pool:
                conn = httplib.HTTPConnection(host, source_address=(ip, 0))
                cls.conn_map[host].append(conn)
            conns = cls.conn_map[host]
            
        return get_random_obj(conns)


def get_data(hostname, method="GET", url=None, body=None):
    #conn = httplib.HTTPConnection(hostname)
    conn = httplib.HTTPConnection(hostname, source_address=(get_random_obj(ip_pool), 0))
    headers = {"User-Agent": "spider"}
    conn.request(method, url + "?" + body, headers=headers)
    data = conn.getresponse().read()
    return data


def get_keyword_list_data(data):
    temp = dict()
    result = re.findall("\(.*\)", data)
    keywords = eval(result[0])['result']
    if keywords:
        for key in keywords:
            temp[key[0]] = key[1]
    return temp

def get_keyword_list(keyword):
    hostname, url, parms = get_keyword_list_url(keyword)
    data = get_data(hostname, url=url, body=parms)
    global keywords_map
    keywords_map = get_keyword_list_data(data)


def get_relative_list_data(data):
    temp = dict()
    d = pq(data)
    r = [i.values() for i in d("#J_relative ul li a")]
    for i in r:
        parms = urlparse.urlparse(i[1])
        key = urlparse.parse_qs(parms.query, keep_blank_values=1)['q'][0]
        temp[key] = None
    return temp
    
    
def get_relative_list(keyword):
    hostname, url, parms = get_query_url(keyword)
    data = get_data(hostname, url=url, body=parms)
    global relative_map
    relative_map = get_relative_list_data(data)


def get_detail_page(keyword):
    hostname, url, body = get_query_url(keyword)
    get_data(hostname, url=url, body=body)


final_keywords = dict()
def get_relative_detail_page(keyword):
    hostname, url, body = get_query_url(keyword)
    data = get_data(hostname, url=url, body=body)
    relative = get_relative_list_data(data)

    hostname, url, body = get_keyword_list_url(keyword)
    data = get_data(hostname, url=url, body=body)
    keywords = get_keyword_list_data(data)
    
    final_keywords[keyword] = relative.keys() + keywords.keys()
    


if __name__ == '__main__':
    print "PID: ", os.getpid()
    master_key = sys.argv[1]
    
    start = time.time()
    
    pool = Pool(size=1024)
    
    pool.add(gevent.spawn(get_keyword_list, master_key))
    pool.add(gevent.spawn(get_relative_list, master_key))
    pool.join()
    
    print "根据 %s 共得到 %s 个关键词(包括下拉列表和推荐)" % (master_key, len(final_keywords.values()))

    end = time.time()

    count = 1
    for k,v in final_keywords.items():
        for i in v:
            count += 1
    
    print "根据 %s 个关键词最终得到 %s 个关键词" % (len(final_keywords.values())/2, count)

    print "全部完成，整个过程消耗时间：%.2f 秒" % float(end-start)
