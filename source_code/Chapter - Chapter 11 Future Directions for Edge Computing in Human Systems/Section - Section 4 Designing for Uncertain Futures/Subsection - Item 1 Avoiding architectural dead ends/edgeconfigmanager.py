#!/usr/bin/env python3
"""
EdgeConfigManager: fetch remote config, verify HMAC, atomically install,
and provide runtime flags with local fallback. Suitable for offline edges.
"""
from typing import Dict, Optional
import logging, tempfile, os, json, hmac, hashlib, time, urllib.request

logger = logging.getLogger("edge_config")
logger.setLevel(logging.INFO)

class EdgeConfigManager:
    def __init__(self, url: str, cache_path: str, hmac_key: bytes, ttl: int = 300):
        self.url = url
        self.cache_path = cache_path
        self.hmac_key = hmac_key
        self.ttl = ttl  # seconds
        self._cached: Dict = {}
        self._last_fetch = 0

    def _atomic_write(self, path: str, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
        try:
            os.write(fd, data)
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, path)  # atomic on POSIX
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _verify_hmac(self, payload: bytes, signature_hex: str) -> bool:
        mac = hmac.new(self.hmac_key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, signature_hex)

    def fetch(self) -> Dict:
        # Respect TTL and use local cache if fresh
        if time.time() - self._last_fetch < self.ttl and self._cached:
            return self._cached
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                body = resp.read()
                sig = resp.getheader("X-Config-HMAC", "")
                if not self._verify_hmac(body, sig):
                    raise ValueError("HMAC verification failed")
                cfg = json.loads(body.decode("utf-8"))
                # persist atomically for offline resilience
                self._atomic_write(self.cache_path, json.dumps(cfg).encode("utf-8"))
                self._cached = cfg
                self._last_fetch = time.time()
                logger.info("Config fetched and installed")
                return cfg
        except Exception as e:
            logger.warning("Fetch failed, attempting cache: %s", e)
            try:
                with open(self.cache_path, "rb") as f:
                    cfg = json.load(f)
                    self._cached = cfg
                    return cfg
            except Exception as e2:
                logger.error("Cache read failed: %s", e2)
                raise

    def get_flag(self, name: str, default: Optional[object] = None) -> object:
        cfg = self.fetch()
        return cfg.get("flags", {}).get(name, default)

# Example usage in systemd or container entrypoint:
# mgr = EdgeConfigManager("https://cfg.example.local/config", "/var/lib/edge/config.json", b"secret", ttl=60)
# debug = mgr.get_flag("debug_mode", False)