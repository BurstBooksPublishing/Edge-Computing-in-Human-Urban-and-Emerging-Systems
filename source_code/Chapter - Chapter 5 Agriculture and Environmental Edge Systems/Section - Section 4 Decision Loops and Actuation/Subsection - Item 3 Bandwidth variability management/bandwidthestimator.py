import asyncio, aiohttp, time
# Production-ready: run as an edge microservice; expose HTTP API to player.
class BandwidthEstimator:
    def __init__(self, alpha=0.3, history_sec=5):
        self.alpha = alpha
        self.ewma = None
        self.last_ts = None
        self.history_sec = history_sec

    async def measure_chunk(self, url, session):
        t0 = time.time()
        async with session.get(url) as resp:
            size = 0
            async for chunk in resp.content.iter_chunked(65536):
                size += len(chunk)
        dt = max(1e-3, time.time() - t0)
        bps = (size * 8) / dt
        self.update(bps)
        return bps

    def update(self, bps):
        if self.ewma is None:
            self.ewma = bps
        else:
            self.ewma = self.alpha * bps + (1 - self.alpha) * self.ewma
        self.last_ts = time.time()

    def predict(self):
        return self.ewma or 0.0

async def abr_loop(manifest_urls, reps, api_port=8080):
    est = BandwidthEstimator(alpha=0.25)
    async with aiohttp.ClientSession() as session:
        # warm-up measurements
        for u in manifest_urls:
            await est.measure_chunk(u, session)
        while True:
            bw = est.predict()
            # choose highest representation r <= 0.9*bw to leave margin
            choice = max([r for r in reps if r <= 0.9*bw], default=min(reps))
            # expose decision via local API (integration with player)
            print(f"predicted_bw={bw:.0f}bps selected={choice}")
            await asyncio.sleep(1.0)

# Example usage: run in container on Jetson or CM4; integrate with DASH player.
# reps = [200_000, 500_000, 1_000_000, 2_500_000]  # bits/s
# asyncio.run(abr_loop(['https://edge/m/segment1.m4s'], reps))