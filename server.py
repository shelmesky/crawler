#!/usr/bin/python

import gevent
from gevent import wsgi
from gevent.pool import Pool
from gevent.event import Event
from gevent.server import StreamServer
from uuid import uuid4

event_pool = dict()

def create_event():
    ev_id = uuid4()
    ev = Event()
    event_pool[ev_id] = dict()
    event_pool[ev_id]['ev'] = ev
    event_pool[ev_id]['count'] = 0
    return ev, ev_id


def get_count(ev_id):
    item = event_pool[ev_id]
    count = item['count']
    return count


def get_ev(ev_id):
    item = event_pool[ev_id]
    ev = item['ev']
    return ev


def increment_count(ev_id):
    event_pool[ev_id]['count'] += 1


def wsgi_app(env, start_response):
    print env
    #if path == "/query":
    #    ev, ev_id = create_event()
    #    task = dict()
    #    task['task'] = "task"
    #    task['id'] = uuid4()
    #    send_task(task)
    #    task_part = 4
    #    while not get_count(ev_id) == 4:
    #        ev.wait()
    #elif path == "/result":
    #    result = request.get()
    #    ev_id = result['ev_id']
    #    increment_count(ev_id)
    #    ev = get_ev(ev_id)
    #    ev.set()


def handle_stream(sock, address):
    print "TCP: ", address


def start_stream_server():
    server = StreamServer(("0.0.0.0", 9002), handle_stream)
    server.serve_forever()


gevent.spawn(start_stream_server)
wsgi_server = wsgi.WSGIServer(("0.0.0.0", 9001), wsgi_app)
wsgi_server.serve_forever()

