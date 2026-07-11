import os, requests
from dotenv import load_dotenv; load_dotenv()
KEY=os.getenv("GEMINI_API_KEY")
r=requests.get("https://generativelanguage.googleapis.com/v1beta/models?key="+KEY,timeout=60); print("status:",r.status_code)
print([m["name"] for m in r.json().get("models",[]) if "flash" in m["name"]])
