from dotenv import load_dotenv; load_dotenv()
import os, requests
KEY=os.getenv("PPLX_API_KEY"); print("cle:", bool(KEY))
r=requests.post("https://api.perplexity.ai/v1/sonar", headers={"Authorization":"Bearer "+KEY}, json={"model":"sonar","messages":[{"role":"user","content":"prix BTC"}]}, timeout=120)
print("status:", r.status_code); print(r.text[:1000])
