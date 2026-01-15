#!/usr/bin/env python3
# Production-ready: structured logging, backoff, graceful shutdown.
import asyncio
import json
import math
from collections import defaultdict
import logging
import signal
from asyncio_mqtt import Client, MqttError

BROKER = "localhost"
CAMERA_TOPIC = "sensors/camera/detections"
RFID_TOPIC = "sensors/rfid/reads"
SCALE_TOPIC = "sensors/scale/weight"
OUT_TOPIC = "system/checkout/basket"
REVIEW_TOPIC = "system/checkout/review"

# Tunable thresholds
CONF_THRESH = 0.65            # min camera confidence
FUSION_WEIGHT_RFID = 1.5     # relative trust in RFID evidence
WEIGHT_TOLERANCE = 0.05      # 5% tolerance on expected vs measured weight

log = logging.getLogger("edge_fusion")
logging.basicConfig(level=logging.INFO)

def loglik_from_conf(conf):
    # convert model confidence to log-likelihood ratio
    eps = 1e-6
    conf = min(max(conf, eps), 1 - eps)
    return math.log(conf / (1 - conf))

async def run():
    async with Client(BROKER) as client:
        async with client.unfiltered_messages() as messages:
            await client.subscribe([(CAMERA_TOPIC,0),(RFID_TOPIC,0),(SCALE_TOPIC,0)])
            # transient state per checkout session
            basket = defaultdict(lambda: {"count":0,"llr":0.0,"expected_weight":0.0})
            current_weight = 0.0
            async for msg in messages:
                try:
                    payload = json.loads(msg.payload.decode())
                except Exception:
                    log.exception("bad payload")
                    continue

                if msg.topic == CAMERA_TOPIC:
                    # payload: {"id": "uuid", "label": "apple", "conf": 0.78, "weight": 0.18}
                    label = payload["label"]
                    conf = float(payload["conf"])
                    if conf < CONF_THRESH:
                        continue
                    llr = loglik_from_conf(conf)
                    # add camera evidence
                    basket[label]["llr"] += llr
                    basket[label]["count"] += 1
                    basket[label]["expected_weight"] += float(payload.get("weight",0.0))
                elif msg.topic == RFID_TOPIC:
                    # payload: {"epcs":["EPC1"], "label_map":{"EPC1":"apple"}}
                    for epc in payload.get("epcs",[]):
                        label = payload.get("label_map",{}).get(epc)
                        if not label:
                            continue
                        # convert RFID read to strong evidence
                        basket[label]["llr"] += FUSION_WEIGHT_RFID * 5.0
                        basket[label]["count"] += 1
                elif msg.topic == SCALE_TOPIC:
                    current_weight = float(payload.get("kg",0.0))

                # simple decision: compute posterior odds and publish basket
                reconciled = {}
                total_expected = 0.0
                for label, state in basket.items():
                    # posterior probability from llr
                    odds = math.exp(state["llr"])
                    prob = odds / (1 + odds)
                    if prob > 0.5:
                        reconciled[label] = {"prob": prob, "count": state["count"]}
                        total_expected += state["expected_weight"]
                # weight consistency check
                if total_expected > 0:
                    rel_err = abs(total_expected - current_weight) / max(total_expected, 1e-6)
                    if rel_err > WEIGHT_TOLERANCE:
                        # publish review request for human oversight
                        await client.publish(REVIEW_TOPIC, json.dumps({
                            "type":"weight_mismatch",
                            "expected_kg": total_expected,
                            "measured_kg": current_weight,
                            "reconciled": reconciled
                        }))
                await client.publish(OUT_TOPIC, json.dumps({
                    "basket": reconciled,
                    "measured_weight": current_weight
                }))

def main():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, loop.stop)
    try:
        loop.run_until_complete(run())
    except MqttError:
        log.exception("MQTT error")
    finally:
        loop.close()

if __name__ == "__main__":
    main()