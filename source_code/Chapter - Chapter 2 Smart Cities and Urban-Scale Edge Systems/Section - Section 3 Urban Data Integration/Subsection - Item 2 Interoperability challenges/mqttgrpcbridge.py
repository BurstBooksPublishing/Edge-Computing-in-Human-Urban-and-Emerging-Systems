#!/usr/bin/env python3
import json, time, logging
import paho.mqtt.client as mqtt
import grpc
from retry import retry  # small, robust retry helper (pip install retry)
import MyTelemetry_pb2 as mt  # generated protobuf messages
import fusion_pb2_grpc as fg  # generated gRPC stubs

BROKER='mqtt.city.local'
TOPIC='sensors/+/telemetry'
FUSION_ADDR='fusion.city.local:50051'
TLS_PARAMS={'ca_certs':'/etc/ssl/ca.pem'}  # example TLS config

logging.basicConfig(level=logging.INFO)

def json_to_proto(payload: dict) -> mt.Telemetry:
    # Unit normalization and minimal semantic mapping
    t=mt.Telemetry()
    t.device_id = payload.get('id','')
    # convert Celsius to Kelvin example
    if 'temp_c' in payload:
        t.temperature_k = float(payload['temp_c']) + 273.15
    if 'ts' in payload:
        t.timestamp = int(payload['ts'])
    return t

@retry(tries=5, delay=1, backoff=2)  # simple backoff for transient failures
def send_to_fusion(stub, proto_msg):
    req = fg.IngestRequest(payload=proto_msg.SerializeToString())
    # unary RPC; production should use streaming when high throughput is needed
    resp = stub.Ingest(req, timeout=2.0)
    return resp

def on_connect(client, userdata, flags, rc):
    logging.info('MQTT connected rc=%s', rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        proto = json_to_proto(payload)
        # blocking send; consider batching for throughput/energy tradeoffs
        send_to_fusion(userdata['stub'], proto)
    except Exception as e:
        logging.exception('Processing failure: %s', e)

def main():
    # gRPC channel with TLS; choose appropriate credentials in production
    creds = grpc.ssl_channel_credentials(open(TLS_PARAMS['ca_certs'],'rb').read())
    channel = grpc.secure_channel(FUSION_ADDR, creds)
    stub = fg.FusionStub(channel)

    client = mqtt.Client(userdata={'stub':stub})
    client.tls_set(**TLS_PARAMS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 8883)
    client.loop_forever()

if __name__ == '__main__':
    main()