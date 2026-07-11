#!/usr/bin/env python3
"""Test de debug pour diagnostiquer l'auth Revolut X."""
import time
import base64
import requests
from revolut_x import RevolutX

c = RevolutX()

ts = str(int(time.time() * 1000))
method = "GET"
full_path = "/api/1.0/balances"
query = ""
body = ""

message = f"{ts}{method}{full_path}{query}{body}".encode()
sig = base64.b64encode(c.private_key.sign(message)).decode()

print("timestamp:", ts)
print("message:", message)
print("signature:", sig[:40] + "...")
print("api_key:", c.api_key[:10] + "...")

url = "https://revx.revolut.com" + full_path
headers = {
    "X-Revx-API-Key": c.api_key,
    "X-Revx-Timestamp": ts,
    "X-Revx-Signature": sig,
    "Accept": "application/json",
}
print("\n--- Requête ---")
print("URL:", url)
print("Headers:", {k: (v[:30] + "..." if len(v) > 30 else v) for k, v in headers.items()})

r = requests.get(url, headers=headers, timeout=15)
print("\n--- Réponse ---")
print("HTTP:", r.status_code)
print("content-type:", r.headers.get("content-type"))
print("body[:500]:", r.text[:500])
