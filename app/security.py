from jose import jwt
from jose.exceptions import JWTError
from datetime import datetime, timezone

def verify_qr_token(qr_token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(qr_token, secret, algorithms=["HS256"])
    except JWTError:
        raise ValueError("INVALID_TOKEN")

    now = datetime.now(timezone.utc).timestamp()
    exp = payload.get("exp")
    if exp is None or now > float(exp):
        raise ValueError("EXPIRED")

    # Required claims
    for k in ["ticket_id", "event_id", "org_id", "nonce"]:
        if k not in payload:
            raise ValueError("INVALID_TOKEN")

    return payload
