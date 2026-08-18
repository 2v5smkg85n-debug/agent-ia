#!/usr/bin/env python3
"""Test rapide Gemini API."""
import os, requests, json
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("GEMINI_API_KEY")
print(f"Gemini key: {key[:10]}..." if key else "GEMINI_API_KEY: MISSING")

if not key:
    exit()

model = "gemini-2.5-flash"
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

print(f"\nTest API call to {model}...")
try:
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": "Dis bonjour en 3 mots"}]}],
            "generationConfig": {"temperature": 0.1}
        },
        timeout=30
    )
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text[:500]}")
    else:
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Response: {text}")
except Exception as e:
    print(f"Exception: {e}")

# Test avec gemini-2.5-flash
print(f"\nTest avec gemini-2.5-flash...")
try:
    url2 = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    r2 = requests.post(
        url2,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": "Dis bonjour en 3 mots"}]}],
            "generationConfig": {"temperature": 0.1}
        },
        timeout=30
    )
    print(f"Status: {r2.status_code}")
    if r2.status_code != 200:
        print(f"Error: {r2.text[:500]}")
    else:
        data2 = r2.json()
        text2 = data2["candidates"][0]["content"]["parts"][0]["text"]
        print(f"Response: {text2}")
except Exception as e:
    print(f"Exception: {e}")
