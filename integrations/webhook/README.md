# Generic webhook adapter (stub)

Not implemented. Documented for the adapter shape.

## Required env vars

```bash
WEBHOOK_URL=       # outbound notification target
WEBHOOK_SECRET=    # HMAC shared secret (recommended for inbound POSTs)
```

## Sketch — outbound only

```python
# integrations/webhook/client.py
import os, requests
def notify(title: str, body: str) -> None:
    url = os.environ["WEBHOOK_URL"]
    requests.post(url, json={"title": title, "body": body}, timeout=10)
```

## Sketch — inbound (Flask / FastAPI)

```python
# integrations/webhook/app.py
from fastapi import FastAPI, Request, HTTPException
import hmac, hashlib, os
from . import client

app = FastAPI()
SECRET = os.environ["WEBHOOK_SECRET"].encode()

@app.post("/iris")
async def on_webhook(req: Request):
    sig = req.headers.get("X-Iris-Signature", "")
    body = await req.body()
    expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401)
    return {"status": client.format_status()}
```
