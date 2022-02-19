import json
import getpass
from pprint import pprint
from pathlib import Path
import os
import asyncio
from layz_spa.auth import Auth
from layz_spa.spa import Spa
from layz_spa.errors import Error

import paho.mqtt.client as paho

mqtt_host = os.environ['MQTT_HOST']
mqtt_port = int(os.environ['MQTT_PORT'])
mqtt_topic = os.environ['MQTT_TOPIC']
loop_seconds = int(os.environ['LOOP_SECONDS'])
email = os.environ["LAYZSPA_EMAIL"]
password = os.environ["LAYZSPA_PASSWORD"]

mqtt = paho.Client("layzspa_watchdog")
mqtt.connect(mqtt_host, mqtt_port, 60)

def mqtt_send(payload):
    try:
        mqtt.publish(mqtt_topic, payload)
    except Exception as e:
        print (e)
        mqtt.connect(mqtt_host, mqtt_port, 60)
        mqtt.publish(mqtt_topic, payload)


async def auth():
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

async def update():
    (spa,online) = await auth()

    await spa.update_status()

    d = {k: v for k, v in spa.__dict__.items() if k != 'api'}
    d['updated_at'] = str(d['updated_at'])
    d['online'] = online
    mqtt.publish(mqtt_topic, json.dumps(d))

async def main():
    loop = asyncio.get_running_loop()
    while True:
        mqtt.loop(.5)
        await update()
        await asyncio.sleep(loop_seconds)

if __name__ == "__main__":
    asyncio.run(main())
