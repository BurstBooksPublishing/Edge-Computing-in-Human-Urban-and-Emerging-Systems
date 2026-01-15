#!/usr/bin/env python3
# Minimal production-ready gossip: UDP, SHA256 digests, anti-entropy, asyncio.
import asyncio, socket, hashlib, json, time
BCAST_ADDR = ('224.0.0.251', 50000)   # use multicast for local discovery
ANTI_ENTROPY = 5.0                    # seconds between anti-entropy rounds

def digest(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

class GossipAgent:
    def __init__(self, node_id, state):
        self.node_id = node_id
        self.state = state
        self.state_ts = time.time()
        self.peers = {}                # addr->last_seen
        self.sock = self._make_socket()

    def _make_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(('', BCAST_ADDR[1]))
        mreq = socket.inet_aton(BCAST_ADDR[0]) + socket.inet_aton('0.0.0.0')
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)
        return sock

    async def start(self):
        loop = asyncio.get_running_loop()
        loop.create_task(self._recv_loop())
        loop.create_task(self._anti_entropy_loop())

    async def _recv_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            data, addr = await loop.sock_recvfrom(self.sock, 65536)
            try:
                msg = json.loads(data.decode())
            except Exception:
                continue
            self.peers[addr] = time.time()
            if msg.get('type') == 'DIGEST':
                # reply with state if digest differs
                if msg.get('digest') != digest(self.state):
                    await loop.sock_sendto(self.sock, json.dumps({
                        'type':'STATE','node':self.node_id,'state':self.state,'ts':self.state_ts
                    }).encode(), addr)
            elif msg.get('type') == 'STATE':
                # accept fresher state
                if msg.get('ts',0) > self.state_ts:
                    self.state = msg['state']
                    self.state_ts = msg['ts']

    async def _anti_entropy_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(ANTI_ENTROPY)
            msg = json.dumps({'type':'DIGEST','node':self.node_id,'digest':digest(self.state)}).encode()
            try:
                await loop.sock_sendto(self.sock, msg, BCAST_ADDR)
            except Exception:
                pass

if __name__ == '__main__':
    import sys
    node = sys.argv[1] if len(sys.argv)>1 else 'node-'+str(int(time.time()))
    state = {'status':'ok','load':0.0}
    agent = GossipAgent(node, state)
    asyncio.run(agent.start())  # integrate with local service supervisor (systemd/container)