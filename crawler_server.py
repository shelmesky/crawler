#!/usr/bin/python                                                                                                                                                                         
#--encoding: utf-8--


import gevent
from gevent.pool import Pool
from gevent import wsgi
from gevent.event import Event
from gevent import socket
from gevent import monkey
monkey.patch_all()

import time                                                                                                                                                                               
import re                                                                                                                                                                                 
import httplib                                                                                                                                                                            
import urllib                                                                                                                                                                             
import random                                                                                                                                                                             
import os                                                                                                                                                                                 
try:                                                                                                                                                                                      
    import simplejson as json                                                                                                                                                             
except ImportError:
    import json
import threading
import Queue

from uuid import uuid4
from prettytable import PrettyTable
from send_task import SendTaskClient

import server_settings
import client_settings

import sys
reload(sys)
sys.setdefaultencoding('UTF-8')

keywords_map = None
relative_map = None
ip_pool = ["180.153.152.37", "180.153.152.66", "180.153.152.67"]
ip_pool = ["180.153.152.37"]
regex_relative = re.compile("relatedSearch.*search\?q=(.*)&")
regex_keywords = re.compile("\((.*)\)")
regex_goods = re.compile('result-info">(\d+)')
regex_dealing = re.compile('col\sdealing">\\xd7\\xee\\xbd\\xfc(.*)\\xc8\\xcb\\xb3\\xc9\\xbd\\xbb</div>')
queue = Queue.Queue()
running = False
event_pool = dict()
self_weight = 1


class EventManager(object):
    @staticmethod
    def create_event():
        ev_id = uuid4()
        ev = Event()
        event_pool[ev_id] = dict()
        event_pool[ev_id]['ev'] = ev
        event_pool[ev_id]['count'] = 0
        return ev, ev_id
    
    @staticmethod
    def get_count(ev_id):
        item = event_pool[ev_id]
        count = item['count']
        return count
    
    @staticmethod
    def get_ev(ev_id):
        item = event_pool[ev_id]
        ev = item['ev']
        return ev
    
    @staticmethod
    def increment_count(ev_id):
        event_pool[ev_id]['count'] += 1


def get_node_jobs(lists):
    """
    根据不同的权重，分割列表(不定长)
    """
    nodes = client_settings.nodes
    total_weight = 0.0
    for node in nodes:
        total_weight += node[1]
    
    jobs_length = len(lists)
    
    node_jobs = list()
    cursor = 0
    process_first = 0
    for node in nodes:
        if node[1] != 0:
            temp = {}
            temp['address'] = node[0]
            part = int(node[1] / total_weight * jobs_length)
            temp['parts'] = lists[process_first if not process_first else cursor : cursor + part]
            cursor = part
            process_first = 1
            node_jobs.append(temp)
    
    return node_jobs


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
        initiative_id = "tbindexz_20130523"
    )
    hostname = "s.taobao.com"
    url = "/search"
    return hostname, url, urllib.urlencode(parms)


def get_data(hostname, method="GET", url=None, body=None):
    #conn = httplib.HTTPConnection(hostname, source_address=(get_random_obj(ip_pool), 0))
    conn = httplib.HTTPConnection(hostname)
    headers = {"User-Agent": "curl 7.22.0"}
    headers = {'Accept-Language':'zh-cn', \
              'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.22 (KHTML, like Gecko) Ubuntu Chromium/25.0.1364.160 Chrome/25.0.1364.160 Safari/537.22'} 
    conn.request(method, url + "?" + body, headers=headers)
    data = conn.getresponse().read()
    conn.close()
    return data


def get_keyword_list_data(data):
    temp = dict()
    result = regex_keywords.findall(data)
    keywords = json.loads(result[0])['result']
    if keywords:
        for key in keywords:
            temp[urllib.unquote(key[0])] = key[1]
    return temp


def get_keyword_list(keyword):
    hostname, url, parms = get_keyword_list_url(keyword)
    data = get_data(hostname, url=url, body=parms)
    global keywords_map
    keywords_map = get_keyword_list_data(data)


def get_relative_list_data(data):
    temp = dict()
    r = regex_relative.findall(data)
    for i in r:
        temp[urllib.unquote(i)] = None
    return temp
    
    
def get_relative_list(keyword):
    hostname, url, parms = get_query_url(keyword)
    data = get_data(hostname, url=url, body=parms)
    global relative_map
    relative_map = get_relative_list_data(data)


final_keywords = dict()
def get_final_keywords(keyword):
    hostname, url, body = get_query_url(keyword)
    data = get_data(hostname, url=url, body=body)
    relative = get_relative_list_data(data)

    hostname, url, body = get_keyword_list_url(keyword)
    data = get_data(hostname, url=url, body=body)
    keywords = get_keyword_list_data(data)
    
    final_keywords[keyword] = relative.keys() + keywords.keys()


final_dealing = dict()
def get_detail_page(keyword):
    hostname, url, body = get_query_url(keyword)
    data = get_data(hostname, url=url, body=body)
    queue.put_nowait((keyword, data))

class CalDealing(threading.Thread):
    def __init__(self, queue):
        super(CalDealing, self).__init__()
        self.queue = queue
    
    def run(self):
        i=1
        while 1:
            keyword, data = self.queue.get(True)
            if keyword == None: break
            i+=1
            # dealing_total: 前40个商品的销售总量
            # goods_amount: 每个关键词的宝贝总数
            dealing_total = sum(map(int, regex_dealing.findall(data)))
            goods_amount = regex_goods.findall(data)
            goods_amount = goods_amount[0] if goods_amount else 0
            #final_dealing[str(i) + ":" + urllib.unquote(keyword)] = dealing_total
            final_dealing[urllib.unquote(keyword)] = (dealing_total, goods_amount)


def send_task(address, parts):
    client = SendTaskClient(address)
    client.send_task(parts)
    return client.recv_response()


def main(main_keyword):
    running = True
    master_key = main_keyword
    f = lambda i,s: [i[x:x+s] for x in xrange(0, len(i), s)]
    split_size = 5
    
    start = time.time()
    
    thread_dealing = CalDealing(queue)
    thread_dealing.start()
    
    pool = Pool(size=32)
    
    pool.add(gevent.spawn(get_keyword_list, master_key))
    pool.add(gevent.spawn(get_relative_list, master_key))
    pool.join()
    

    ##########################################################

    allkeys = keywords_map.keys() + relative_map.keys()
    random.shuffle(allkeys)
    splited = f(allkeys, split_size)
    for keys in splited:
        pool = Pool(split_size)
        [pool.add(pool.spawn(get_final_keywords, key)) for key in keys]
        pool.join()

    ##########################################################

    def decode_print(v):
        try:
            return v.decode('GBK').encode('UTF-8')
        except:
            return v.encode('UTF-8')

    count = 1
    last_list = list()
    for k,v in final_keywords.items():
        for i in v:
            last_list.append(i)
            count += 1

    last_list = {}.fromkeys(last_list).keys() 

    ##########################################################

    random.shuffle(last_list)
    node_jobs = get_node_jobs(last_list)
    jobs = []
    for node in node_jobs:
        jobs.append(gevent.spawn(send_task, node['address'], str(node['parts']).encode('hex')))
    
    gevent.joinall(jobs)
    
    for job in jobs:
        print job.value.decode('hex')
    
    return

    splited = f(last_list, split_size)

    for i in splited:
                pool = Pool(split_size)
                [pool.add(pool.spawn(get_detail_page, key)) for key in i]
                pool.join()

    queue.put((None, None))
    
    ##########################################################

    end = time.time()
    
    global final_dealing
    thread_dealing.join()
    final_dealing = sorted(final_dealing.items(), key=lambda x: x[1][0], reverse=True)
    t = PrettyTable(["ID", "名称", "销售总量", "宝贝总量"])
    t.align[1] = 'l'
    t.align[2] = 'r'
    t.align[3] = 'r'
    t.left_padding = 1
    for i in final_dealing:
        t.add_row([final_dealing.index(i), decode_print(i[0]), str(i[1][0]), str(i[1][1])])
    running = False
    return count, last_list, end-start, t


def not_found(start_response):
    start_response('404 Not Found', [('Content-Type', 'text/html')])
    return ['<h1>Not Found</h1>']


def main_app(env, start_response):
    path = env['PATH_INFO']
    url_query = re.compile('/query/(.*)')
    url_result= re.compile('/result/(.*)')
    if path.startswith("/query"):
        keyword = url_query.findall(path)
        if not keyword:
            return not_found(start_response)
        
        main(keyword[0])
        return
        #count, last_list, times, t = main(keyword[0])
        tip1 = "根据 %s 共得到 %s 个关键词(包括下拉列表和推荐)" % (keyword, len(final_keywords.values()))
        tip2 = "根据 %s 个关键词最终得到 %s 个关键词" % (len(final_keywords.values()), count)
        tip3 = "去除重复项后共 %s 个关键词" % len(last_list)
        tip4 = "全部完成，整个过程消耗时间：%.2f 秒" % float(times)
        
        start_response('200 OK', [('Content-Type', 'text/html')])
        
        return ["%s<br />%s<br />%s<br />%s<br /><pre>%s</pre>" % (tip1, tip2, tip3, tip4, t)]
    else:                                                                                                                  
        return not_found(start_response)

if __name__ == '__main__':
    port = 8088
    print "WSGI Server listening on TCP: %s" % port
    server = wsgi.WSGIServer(('', port), main_app)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print "Server exit..."
        server.stop()

