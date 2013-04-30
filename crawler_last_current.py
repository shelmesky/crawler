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
#ip_pool = ["180.153.152.37", "180.153.152.66"]
#ip_pool = ["180.153.152.37", "180.153.152.66", "180.153.152.67"]
ip_pool = ["180.153.152.37"]
regex = re.compile("relatedSearch.*search\?q=(.*)&", data)

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
    #headers = {"User-Agent": "spider"}
    headers = {'Accept-Language':'zh-cn','Accept-Encoding': 'gzip, deflate','User-Agent': 'Mozilla/4.0 (compatible; MSIE 6.0;Windows NT 5.0)','Connection':' Keep-Alive' } 
    conn.request(method, url + "?" + body, headers=headers)
    if hostname == "s.taobao.com":
        data = conn.getresponse().read()
    else:
        data = conn.getresponse().read()
    conn.close()
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
    r = regex.findall(data)
    for i in r:
        temp[i] = None
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
def get_final_keywords(keyword):
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
    

    ##########################################################

    [pool.add(pool.spawn(get_final_keywords, key)) for key in keywords_map.keys()]
    [pool.add(pool.spawn(get_final_keywords, key)) for key in relative_map.keys()]
    pool.join()

    ##########################################################

    def decode_print(v):
        return
        try:
            print v.decode('GBK')
        except:
            print v

    count = 1
    last_list = list()
    for k,v in final_keywords.items():
        decode_print(k)
        #print "-" * 10
        for i in v:
            decode_print(i)
            last_list.append(i)
            count += 1
        #print
        #print

    print "根据 %s 共得到 %s 个关键词(包括下拉列表和推荐)" % (master_key, len(final_keywords.values()))
    
    print "根据 %s 个关键词最终得到 %s 个关键词" % (len(final_keywords.values()), count)

    ##########################################################

    split_size = 18
    f = lambda i,s: [i[x:x+s] for x in xrange(0, len(i), s)]
    splited = f(last_list, split_size)

    for i in splited:
                pool = Pool(split_size)
                [pool.add(pool.spawn(get_detail_page, key)) for key in i]
                pool.join()

    ##########################################################

    end = time.time()
    print "全部完成，整个过程消耗时间：%.2f 秒" % float(end-start)
