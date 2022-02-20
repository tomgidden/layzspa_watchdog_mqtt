#!/usr/bin/env python

import sys

import paho.mqtt.client as mqtt
import blinkt
import time
import datetime
import threading
import signal

MQTT_SERVER = "mqtt.home"
MQTT_PORT = 1883

MQTT_TOPIC = "/blinkt1"
MQTT_PING_TOPIC = "/pulse"
MQTT_RESTART_TOPICS = [
    "/restart",
    "/blinkt1/restart"
]
MQTT_PONG_TOPIC = "/blinkt1/watchdog"

# Set these to use authorisation
MQTT_USER = None
MQTT_PASS = None

"""
rgb,<pixel>,<r>,<g>,<b> - Set a single pixel to an RGB colour. Example: rgb,1,255,0,255
clr - Clear Blinkt!
"""

exiting = False

leds = None
lock = threading.Lock()

last_pinged = datetime.datetime.now()

def clr_leds ():
    global leds

    leds = [(0,0,0,None,None,None,0,None) for x in range(blinkt.NUM_PIXELS)]
    for x in range(blinkt.NUM_PIXELS):
        leds[x] = (0,0,0,0,0,0,0,0)

clr_leds()

def set_led(x, r1, g1, b1, r2, g2, b2, dur):
    leds[x] = (r1,g1,b1,r2,g2,b2,dur,time.time()+dur)

class LEDUpdateJob(threading.Thread):
    def __init__(self, interval=0.1):
        self.event = threading.Event()
        self.interval = interval
        super(LEDUpdateJob,self).__init__()

    def run(self):
        while not self.event.wait(self.interval):
            if datetime.datetime.now() - last_pinged > datetime.timedelta(minutes=10):
                sys.exit(1)

            if lock.acquire(False):
                update = False
                now = time.time()
                for x in range(blinkt.NUM_PIXELS):
                    r1, g1, b1, r2, g2, b2, dur, unt = leds[x]
                    if dur is not None:
                        if dur != 0:
                            if (now > unt):
                                update = True
                                blinkt.set_pixel(x, r1, g1, b1)
                                leds[x] = (r2,g2,b2,r1,g1,b1,dur,now+dur)
                        else:
                            update = True
                            blinkt.set_pixel(x, r1, g1, b1)
                            leds[x] = (r1,g1,b1,None,None,None,None,None)

                if update is True: blinkt.show()
                lock.release()

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe(MQTT_TOPIC)
    client.subscribe(MQTT_PING_TOPIC)
    for x in MQTT_RESTART_TOPICS:
        client.subscribe(x)

def handle_cmd (cmd, msg):
    try:
        data = cmd.split(',')
    except Exception as e:
        print (e)
        return

    command = data.pop(0)

    if command == "clr" and len(data) == 0:
        clr_leds()
        blinkt.clear()
        return True

    if command == "rgb" and len(data) == 4:
        data = [data[0],
                data[1], data[2], data[3],
                data[1], data[2], data[3],
                0]

    if command == "rgb" and len(data) == 8:
        try:
            pixel = data.pop(0)
            if pixel == "*":
                pixel = None
            else:
                pixel = int(pixel)
                if pixel > 7:
                    print("Pixel out of range: " + str(pixel))
                    return False

            r1 = int(data[0]) & 0xff
            g1 = int(data[1]) & 0xff
            b1 = int(data[2]) & 0xff
            r2 = int(data[3]) & 0xff
            g2 = int(data[4]) & 0xff
            b2 = int(data[5]) & 0xff
            dur = float(data[6])

        except ValueError:
            print("Malformed command: " + str(msg.payload))
            return False

        if pixel is None:
            for x in range(blinkt.NUM_PIXELS):
                set_led(x, r1, g1, b1, r2, g2, b2, dur)
                return True
        else:
            set_led(pixel, r1, g1, b1, r2, g2, b2, dur)
            return True

    return False


def on_message(client, userdata, msg):

    if msg.topic == MQTT_PING_TOPIC:
        client.publish(MQTT_PONG_TOPIC, 'ping')
        last_pinged = datetime.datetime.now()
        return True

    if msg.topic in MQTT_RESTART_TOPICS:
        sys.exit(1)

    if lock.acquire(True):
        cmds = msg.payload.decode("utf-8").split(';')
        change = False

        for cmd in cmds:
            if handle_cmd(cmd, msg):
                change = True

        if change:
            blinkt.show()
        lock.release()

    return


blinkt.set_clear_on_exit()

l = LEDUpdateJob(0.1)
l.daemon = True
l.start()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

if MQTT_USER is not None and MQTT_PASS is not None:
    print("Using username: {un} and password: {pw}".format(un=MQTT_USER, pw="*" * len(MQTT_PASS)))
    client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)

client.connect(MQTT_SERVER, MQTT_PORT, 60)

client.loop_forever()
