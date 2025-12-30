# scripts/mint_token.py
import os  # read environment variables
import uuid  # generate a unique nonce
import argparse  # parse CLI args
from datetime import datetime, timedelta, timezone  # create an expiry timestamp
from jose import jwt  # create a JWT token

def main() -> None:  # main entrypoint
    parser = argparse.ArgumentParser()  # CLI parser
    parser.add_argument("--ticket-id", required=True)  # ticket id to embed
    parser.add_argument("--event-id", required=True)  # event id to embed
    parser.add_argument("--org-id", required=True)  # org id to embed
    parser.add_argument("--ttl-minutes", type=int, default=60)  # token lifetime
    args = parser.parse_args()  # parse args

    secret = os.environ.get("TICKET_SIGNING_SECRET", "dev_secret_change_me")  # signing secret
    nonce = str(uuid.uuid4())  # unique token nonce for replay protection

    exp_dt = datetime.now(timezone.utc) + timedelta(minutes=args.ttl_minutes)  # expiry datetime
    exp_ts = int(exp_dt.timestamp())  # expiry as unix seconds

    payload = {  # JWT claims/payload
        "ticket_id": args.ticket_id,  # required by verifier
        "event_id": args.event_id,  # required by verifier
        "org_id": args.org_id,  # required by verifier
        "nonce": nonce,  # required by verifier (used for replay protection)
        "exp": exp_ts,  # required by verifier (expiry)
    }

    token = jwt.encode(payload, secret, algorithm="HS256")  # sign token
    print(token)  # output token to stdout

if __name__ == "__main__":  # run as script
    main()  # call main
