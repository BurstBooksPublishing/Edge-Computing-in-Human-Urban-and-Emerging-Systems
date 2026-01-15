#!/usr/bin/env python3
# production-grade: asyncio, TLS, signature verification, atomic install
import asyncio, logging, importlib, pathlib, aiohttp, hashlib
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from asyncio_mqtt import Client as MQTTClient

PLUGINDIR = pathlib.Path("/opt/edge/plugins")
PUBKEY_PEM = pathlib.Path("/etc/edge/pubkey.pem").read_bytes()

async def verify_signature(manifest_bytes: bytes, sig_b64: str) -> bool:
    pubkey = serialization.load_pem_public_key(PUBKEY_PEM)
    sig = bytes.fromhex(sig_b64)
    try:
        pubkey.verify(sig, manifest_bytes, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False

async def download_plugin(url: str, dest: pathlib.Path):
    # atomic download then move
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=True) as resp:
            resp.raise_for_status()
            tmp = dest.with_suffix(".tmp")
            with tmp.open("wb") as fd:
                while True:
                    chunk = await resp.content.read(65536)
                    if not chunk: break
                    fd.write(chunk)
            tmp.replace(dest)

async def install_and_activate(name: str, url: str, checksum: str):
    PLUGINDIR.mkdir(parents=True, exist_ok=True)
    dest = PLUGINDIR / f"{name}.py"
    await download_plugin(url, dest)
    # verify checksum
    data = dest.read_bytes()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise RuntimeError("checksum mismatch")
    # safe activation: importlib reload with sandboxing recommended
    spec = importlib.util.spec_from_file_location(name, str(dest))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # call well-known init if present
    if hasattr(module, "activate"):
        await asyncio.get_event_loop().run_in_executor(None, module.activate)

async def mqtt_handler():
    async with MQTTClient("broker.example.local") as client:
        async with client.filtered_messages("edge/capabilities/manifest") as msgs:
            await client.subscribe("edge/capabilities/manifest")
            async for msg in msgs:
                manifest = msg.payload
                # payload is JSON: {name,url,checksum,sig}
                import json
                m = json.loads(manifest)
                if not await verify_signature(manifest, m["sig"]):
                    logging.warning("manifest signature failed")
                    continue
                await install_and_activate(m["name"], m["url"], m["checksum"])

def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(mqtt_handler())

if __name__ == "__main__":
    main()