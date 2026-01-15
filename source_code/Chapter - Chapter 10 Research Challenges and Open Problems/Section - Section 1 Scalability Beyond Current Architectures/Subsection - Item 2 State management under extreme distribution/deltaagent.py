import asyncio, json, time
from asyncio_mqtt import Client  # pip install asyncio-mqtt

BROKER='mqtt.example.local'
TOPIC='edge/state/delta'
PERSIST_FILE='state.wal'  # persistent write-ahead log

def now_ts(): return int(time.time()*1000)

class StateStore:
    def __init__(self): self.store={}, self.load()
    def load(self): 
        try:
            with open(PERSIST_FILE,'r') as f:
                for line in f: self.apply(json.loads(line))
        except FileNotFoundError: pass
    def wal(self,delta):
        with open(PERSIST_FILE,'a') as f: f.write(json.dumps(delta)+'\n')
    def apply(self,delta):
        # LWW per key: {key:{'v':..., 'ts':...}}
        for k,kv in delta.items():
            cur=self.store.get(k)
            if (cur is None) or (kv['ts']>cur['ts']): self.store[k]=kv

    def make_delta(self,updates):
        delta={k:{'v':v,'ts':now_ts()} for k,v in updates.items()}
        self.wal(delta); self.apply(delta); return delta

async def publisher(store):
    async with Client(BROKER) as client:
        while True:
            # gather local changes periodically; here simulated
            await asyncio.sleep(1.0)
            updates={}  # populate from sensors/actuators
            if updates:
                delta=store.make_delta(updates)
                await client.publish(TOPIC,json.dumps(delta),qos=1)

async def subscriber(store):
    async with Client(BROKER) as client:
        async with client.unfiltered_messages() as messages:
            await client.subscribe(TOPIC,qos=1)
            async for msg in messages:
                try: store.apply(json.loads(msg.payload.decode()))
                except Exception: pass

async def main():
    store=StateStore()
    await asyncio.gather(publisher(store), subscriber(store))

if __name__=='__main__': asyncio.run(main())