import asyncio, json, ssl, os, numpy as np
from aiohttp import web, ClientSession
import jwt  # PyJWT
from confluent_kafka import Producer

# Load config (secrets via env or secure vault)
JWKS_URL = os.environ['JWKS_URL']
KAFKA_CONF = {'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP'],
              'security.protocol': 'SSL', 'ssl.ca.location': '/etc/certs/ca.pem'}
PRODUCER = Producer(KAFKA_CONF)

async def fetch_jwks(session):
    async with session.get(JWKS_URL, timeout=5) as r:
        return await r.json()

def validate_token(token, jwks):
    # Simplified: find key and verify signature / expiry
    header = jwt.get_unverified_header(token)
    # key selection omitted for brevity
    return jwt.decode(token, jwks['keys'][0], algorithms=[header['alg']])

def abac_allows(claims, policy, resource):
    # Policy is a JSON structure mapping roles->allowed resources
    role = claims.get('role')
    return resource in policy.get(role, [])

def laplace_noise(value, sensitivity, eps):
    scale = sensitivity / eps
    return float(value + np.random.laplace(0.0, scale))

async def handle_publish(request):
    token = request.headers.get('Authorization','').split()[-1]
    payload = await request.json()
    async with ClientSession() as s:
        jwks = await fetch_jwks(s)
    claims = validate_token(token, jwks)  # throws on invalid
    policy = json.load(open('/etc/abac/policy.json'))
    target = payload['target_agency']
    if not abac_allows(claims, policy, target):
        raise web.HTTPForbidden()
    # Transform numeric fields per policy
    if policy[target].get('dp'):
        eps = policy[target]['dp']['epsilon']
        sens = policy[target]['dp']['sensitivity']
        payload['aggregate_count'] = laplace_noise(payload['aggregate_count'], sens, eps)
    PRODUCER.produce(f"agency-{target}", json.dumps(payload).encode('utf-8'))
    PRODUCER.flush()
    return web.json_response({'status':'ok'})

app = web.Application()
app.router.add_post('/publish', handle_publish)
web.run_app(app, port=8080)