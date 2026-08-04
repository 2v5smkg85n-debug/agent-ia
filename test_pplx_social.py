#!/usr/bin/env python3
"""Test rapide Perplexity API pour social_consensus."""
import os, requests, json
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("PPLX_API_KEY")
print(f"Key: {key[:10]}...")

print("\nTest API call...")
try:
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [
                {"role": "system", "content": "Tu es un analyste crypto."},
                {"role": "user", "content": "Quels sont les derniers posts de @PeterLBrandt sur X/Twitter concernant le Bitcoin? Extrais les signaux: asset, direction (bullish/bearish), confidence. Reponds en JSON: {\"signaux\": [...]}"}
            ],
            "temperature": 0.1,
        },
        timeout=45,
    )
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text[:500]}")
    else:
        data = r.json()
        contenu = data["choices"][0]["message"]["content"]
        print(f"Response ({len(contenu)} chars):")
        print(contenu[:500])
except Exception as e:
    print(f"Exception: {e}")
