#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch idempotent: ajoute la route /ia au dashboard_server.py."""
import shutil
import os

FICHIER = os.path.join(os.getcwd(), "dashboard_server.py")
MARKER = "IA-ROUTE-INSTALLE"

with open(FICHIER, "r", encoding="utf-8") as f:
    code = f.read()

if MARKER in code:
    print("[OK] Route /ia deja installee. Rien a faire.")
    raise SystemExit(0)

shutil.copy2(FICHIER, FICHIER + ".bak.ia")
print("[i] Backup: dashboard_server.py.bak.ia")

# 1. import ia_render apres import performance
code = code.replace("import performance\n",
                    "import performance\nimport ia_render  # " + MARKER + "\n", 1)

# 2. route /ia avant le try: d = json.load(...)
ANCRE = "        try:\n            d = json.load(open(DATA_FILE))"
ROUTE = (
    "        # Route /ia : IA avancee (strategies + reflexion)\n"
    "        if parsed.path in ('/ia', '/ai'):\n"
    "            try:\n"
    "                out = ia_render.render_ia(token)\n"
    "            except Exception as e:\n"
    "                out = (\"<html><body style='background:#0d1117;color:#e6edf3;"
    "            font-family:sans-serif;padding:20px'><h2>Erreur page IA</h2>"
    "            <pre>\" + html.escape(str(e)) + \"</pre></body></html>\")\n"
    "            self.send_response(200)\n"
    "            self.send_header('Content-Type', 'text/html; charset=utf-8')\n"
    "            self.end_headers()\n"
    "            self.wfile.write(out.encode())\n"
    "            return\n"
    + ANCRE
)

if ANCRE not in code:
    print("[ECHEC] Ancrage route introuvable.")
    raise SystemExit(1)
code = code.replace(ANCRE, ROUTE, 1)

# 3. lien /ia dans la meta du dashboard principal
LIEN_ANCRE = '<a class="lnk" href="/perf?token={TOKEN}">📈 Performance</a>'
LIEN_NOUV = (LIEN_ANCRE +
             ' · <a class="lnk" href="/ia?token={TOKEN}">🧠 IA</a>')
if LIEN_ANCRE in code:
    code = code.replace(LIEN_ANCRE, LIEN_NOUV, 1)

with open(FICHIER, "w", encoding="utf-8") as f:
    f.write(code)

print("[OK] Route /ia installee dans dashboard_server.py")
print("     Page accessible: http://IP:8765/ia?token=...")
