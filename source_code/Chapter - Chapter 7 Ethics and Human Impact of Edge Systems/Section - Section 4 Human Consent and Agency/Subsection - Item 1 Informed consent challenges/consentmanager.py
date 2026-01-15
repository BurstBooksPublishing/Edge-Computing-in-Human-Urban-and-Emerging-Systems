from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3, jwt, logging

# Configuration (replace with secure key management in production)
JWT_SECRET = "replace_with_hardware_keystore"
JWT_ALGO = "HS256"
DB_PATH = "/var/lib/edge/consent.db"

app = FastAPI()
logging.basicConfig(level=logging.INFO)

def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS audits(time TEXT, action TEXT, subject TEXT, meta TEXT)")
    return conn

db = db_conn()

class ConsentRequest(BaseModel):
    subject_id: str  # user or device id
    scope: str       # data scope e.g. "video:person_count"

@app.post("/consent/issue")
def issue_consent(req: ConsentRequest):
    # create short-lived JWT token encoding consent; audit issuance
    exp = datetime.utcnow() + timedelta(hours=12)
    token = jwt.encode({"sub": req.subject_id, "scope": req.scope, "exp": exp}, JWT_SECRET, algorithm=JWT_ALGO)
    db.execute("INSERT INTO audits VALUES (?,?,?,?)", (datetime.utcnow().isoformat(), "issue", req.subject_id, req.scope))
    db.commit()
    return {"token": token, "expires": exp.isoformat()}

@app.post("/consent/revoke")
def revoke_consent(req: ConsentRequest):
    # revocation recorded in audit log; gateways should check revocation list
    db.execute("INSERT INTO audits VALUES (?,?,?,?)", (datetime.utcnow().isoformat(), "revoke", req.subject_id, req.scope))
    db.commit()
    return {"status": "revoked"}

@app.get("/audit")
def get_audit(limit: int = 100):
    cur = db.execute("SELECT * FROM audits ORDER BY time DESC LIMIT ?", (limit,))
    return [{"time": r[0], "action": r[1], "subject": r[2], "meta": r[3]} for r in cur.fetchall()]

@app.post("/enforce")
def enforce(request: Request):
    # enforced at inference pipeline: verify token in Authorization header
    auth = request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split()[1]
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    db.execute("INSERT INTO audits VALUES (?,?,?,?)", (datetime.utcnow().isoformat(), "access", claims.get("sub"), claims.get("scope")))
    db.commit()
    return {"allowed": True}