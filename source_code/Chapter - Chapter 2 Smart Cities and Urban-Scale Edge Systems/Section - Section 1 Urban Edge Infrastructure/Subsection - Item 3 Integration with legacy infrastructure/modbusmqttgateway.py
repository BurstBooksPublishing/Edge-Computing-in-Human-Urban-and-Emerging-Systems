#!/usr/bin/env python3
import asyncio
import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor
from pymodbus.client.sync import ModbusSerialClient  # sync client used inside executor
from asyncio_mqtt import Client as MQTTClient

DB_PATH = "gateway_store.db"
MODBUS_PORT = "/dev/ttyUSB0"
MODBUS_BAUD = 19200
MQTT_BROKER = "broker.example.com"
MQTT_PORT = 8883
MQTT_TOPIC = "city/traffic/corridor1"

# small threadpool for blocking pymodbus calls
executor = ThreadPoolExecutor(max_workers=2)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, topic TEXT, payload TEXT)")
    conn.commit()
    conn.close()

def modbus_read(address, count):
    # Blocking Modbus RTU read; safe to call from thread executor
    client = ModbusSerialClient(method='rtu', port=MODBUS_PORT, baudrate=MODBUS_BAUD, timeout=1)
    if not client.connect():
        raise ConnectionError("Modbus serial connect failed")
    rr = client.read_holding_registers(address, count, unit=1)
    client.close()
    if rr.isError():
        raise IOError("Modbus read error")
    return rr.registers

async def poll_and_queue():
    while True:
        try:
            registers = await asyncio.get_event_loop().run_in_executor(executor, modbus_read, 0, 10)
            payload = json.dumps({"ts": asyncio.get_event_loop().time(), "regs": registers})
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO outbox(topic,payload) VALUES(?,?)", (MQTT_TOPIC, payload))
            conn.commit(); conn.close()
        except Exception as e:
            # transient errors logged; backoff before retry
            await asyncio.sleep(2)
        await asyncio.sleep(0.2)  # poll period to meet latency budget

async def publish_outbox(mqtt_client):
    while True:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT id,topic,payload FROM outbox ORDER BY id LIMIT 20")
        rows = cur.fetchall()
        for rid, topic, payload in rows:
            try:
                await mqtt_client.publish(topic, payload.encode(), qos=1)
                conn.execute("DELETE FROM outbox WHERE id=?", (rid,))
                conn.commit()
            except Exception:
                # leave row for retry; break to allow reconnect/backoff
                break
        conn.close()
        await asyncio.sleep(1)

async def main():
    init_db()
    backoff = 1
    while True:
        try:
            async with MQTTClient(MQTT_BROKER, port=MQTT_PORT, tls=True) as mq:
                backoff = 1
                await asyncio.gather(poll_and_queue(), publish_outbox(mq))
        except Exception:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    asyncio.run(main())