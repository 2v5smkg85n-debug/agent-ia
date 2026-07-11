import os, requests
from dotenv import load_dotenv
load_dotenv()
KEY=os.getenv("PPLX_API_KEY")
print("cle presente:", bool(KEY))
r=requests.post("https://api.perplexity.ai/v1/sonar",
    headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},
    json={"model":"sonar","messages":[{"role":"user","content":"Quel est le prix du Bitcoin aujourd'hui?"}]},
    timeout=90)
print("status:", r.status_code)
print("REPONSE:", r.text[:1500])
