import os, requests
from dotenv import load_dotenv
load_dotenv()
KEY=os.getenv("GEMINI_API_KEY")
print("cle presente:", bool(KEY))
url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key="+KEY
r=requests.post(url,json={"contents":[{"parts":[{"text":"Dis bonjour en une phrase"}]}]},timeout=60)
print("status:", r.status_code)
print("REPONSE:", r.text[:500])
