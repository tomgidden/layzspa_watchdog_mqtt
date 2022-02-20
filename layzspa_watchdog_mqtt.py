#!/usr/bin/env python

import os
def getenv(k):
    try:
        return os.environ[k]
    except:
        return None

mqtt_host = getenv('MQTT_HOST')
mqtt_port = int(getenv('MQTT_PORT') or 0)
mqtt_topic = getenv('MQTT_TOPIC')
loop_seconds = int(getenv('LOOP_SECONDS') or 60)
email = getenv("LAYZSPA_EMAIL")
password = getenv("LAYZSPA_PASSWORD")
ping_host = getenv('PING_HOST')
ping_delay = int(getenv('PING_DELAY') or 60)
udp_mac = getenv('UDP_MAC')

from sys import exit
import json
import getpass
from pprint import pprint
from pathlib import Path
import asyncio
import threading
import datetime

try:
    from layz_spa.auth import Auth
    from layz_spa.spa import Spa
    from layz_spa.errors import Error
except:
    print ("pip3 install layz_spa for API support")
    email = None
    password = None

import time

import paho.mqtt.client as paho
import ping3
import socket
import binascii
import signal


mqtt = paho.Client("layzspa_watchdog")
mqtt.connect(mqtt_host, mqtt_port, 60)

running = True
debug = True

def ping_main():
    if not ping_host:
        print ("set PING_HOST for ping monitoring")
        return

    while running:
        ping = ping3.ping(ping_host, timeout=10)
        mqtt_send('ping', json.dumps(ping))
        time.sleep(ping_delay)

def udp_main():
    if not udp_mac:
        print ("set UDP_MAC for local network monitoring")
        return

    try:
        UDP_IP = "255.255.255.255"
        UDP_PORT = 12414
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))
        macbytes = binascii.unhexlify(str(udp_mac).replace(':', ''))
    except Exception as e:
        print ("Failed to set up local network monitoring", e)
        return

    while running:
        data, addr = sock.recvfrom(1024)
        if data == b'\x00\x00\x00\x03\x03\x00\x00\x03':
            pass

        else:
            if data[9:15] == macbytes: #b'@\xf5 \xf4\x11\xef':
                status = data[16]
                temp = int(data[17])
                curtemp = int(data[30])
                ok = data[31] != 0
                on   = status & 0b1 != 0
                heat = status & 0b10 != 0
                filt = status & 0b100 != 0
                mass = status & 0b1000 != 0
                lock = status & 0b10000 != 0
                cels = status & 0b1000000 != 0

                d = {
                    'updated_at': str(datetime.datetime.now()),
                    'power': status & 0b1 != 0,
                    'heat_power': status & 0b10 != 0,
                    'filter_power': status & 0b100 != 0,
                    'wave_power': status & 0b1000 != 0,
                    'locked': status & 0b10000 != 0,
                    'temp_set_unit': ("°C" if status & 0b1000000 != 0 else "°F"),
                    'temp_now': curtemp,
                    'temp_set': temp,
                    'heat_temp_reach': curtemp == temp,
                    'ok': ok,
                    'online': True
                };

                mqtt_send('udp', json.dumps(d))
            else:
                print ("Unknown MAC address {} != {}".format(data[9:15], macbytes))


def mqtt_send(topic, payload):
    try:
        if debug: print("{}\t{}".format(topic,payload))

        mqtt.publish(mqtt_topic+'/'+topic, payload)
    except Exception as e:
        print (e)
        mqtt.connect(mqtt_host, mqtt_port, 60)
        mqtt.publish(mqtt_topic+'/'+topic, payload)


async def api_auth():
    cache_file = Path("token.cache")

    try:
        if not cache_file.is_file():
            raise Exception("No file")

        response = json.loads(cache_file.read_text())
        spa = Spa(response["data"]["api_token"], response["devices"][0]["did"])
        online = await spa.is_online()

        return (spa,online)

    except Exception as e:
        print (e)

        auth = Auth()
        response = await auth.get_token(email, password)
        cache_file.write_text(json.dumps(response))
        spa = Spa(response["data"]["api_token"], response["devices"][0]["did"])
        online = await spa.is_online()

        return (spa,online)

async def api_update():
    (spa,online) = await api_auth()

    await spa.update_status()

    d = {k: v for k, v in spa.__dict__.items() if k != 'api'}
    d['updated_at'] = str(d['updated_at'])
    d['online'] = online

    mqtt_send('api', json.dumps(d))

async def api_loop():
    if not email: return

    loop = asyncio.get_running_loop()
    while running:
        await api_update()
        await asyncio.sleep(loop_seconds)

def api_main():
    asyncio.run(api_loop())

def shutdown_handler(signum, frame):
    global U, A, P
    running = False
    U.stop()
    A.stop()
    P.stop()
    mqtt.disconnect()
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGUSR1, shutdown_handler)

if __name__ == "__main__":
    U = threading.Thread(target=udp_main)
    U.daemon = True
    U.start()

    A = threading.Thread(target=api_main)
    A.daemon = True
    A.start()

    P = threading.Thread(target=ping_main)
    P.daemon = True
    P.start()

    mqtt.loop_forever()
