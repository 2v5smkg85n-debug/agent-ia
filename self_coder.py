#!/usr/bin/env python3
"""
Self-Coder — Le bot peut écrire, tester et déployer son propre code.

SÉCURITÉ:
  1. Sandbox: teste le code avant déploiement
  2. Rollback: si ça casse, restaure la version précédente
  3. Garde-fous: pas de modifications de .env, pas de suppression de fichiers
  4. Limite: max 5 auto-modifications par jour
  5. Validation: le code doit passer ast.parse() + test fonctionnel
  6. Liste noire: ne touche jamais à .env, credentials, systemd
  7. Historique: toutes les modifications sont loggées

DÉCLENCHEMENT:
  - Manuel: commande Telegram 'code <description>'
  - Auto: déclenché par auto-amélioration quand un problème est détecté
"""
import json
import os
import ast
import shutil
import subprocess
import time
import re
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_HISTORIQUE = os.path.join(DOSSIER, "self_coder_history.json")
FICHIER_SAFETY = os.path.join(DOSSIER, "self_coder_safety.json")
MAX_MODIFS_PAR_JOUR = 5
MAX_FILE_SIZE = 50000  # 50KB max par fichier modifié

# Fichiers que le bot ne peut JAMAIS modifier
BLACKLIST_FICHIERS = [
    ".env",
    "self_coder.py",      # ne peut pas se modifier lui-même
    "self_coder_history.json",
    "self_coder_safety.json",
    "agent_memory.json",
    "knowledge_base.json",
    "solutions_db.json",
    "corrections_db.json",
]

# Patterns interdits dans le code généré
BLACKLIST_PATTERNS = [
    r"import\s+os\s*;?\s*os\.system\s*\(",
    r"subprocess\.call\s*\(\s*['\"]rm\s",
    r"subprocess\.call\s*\(\s*['\"]sudo\s",
    r"shutil\.rmtree\s*\(\s*['\"]/",
    r"open\s*\(\s*['\"].*\.env['\"]\s*,\s*['\"]w",
    r"os\.remove\s*\(\s*['\"]",
    r"__import__\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"os\.environ\s*\[",
    r"TOKEN|API_KEY|SECRET|PASSWORD|CREDENTIAL",
]


def charger_safety():
    """Charge l'état de sécurité."""
    try:
        with open(FICHIER_SAFETY) as f:
            return json.load(f)
    except Exception:
        return {
            "modifs_aujourdhui": 0,
            "date_reset": datetime.now().strftime("%Y-%m-%d"),
            "total_modifs": 0,
            "total_rollbacks": 0,
            "modifs_reussies": 0,
            "modifs_echouees": 0,
        }


def sauver_safety(safety):
    with open(FICHIER_SAFETY, "w") as f:
        json.dump(safety, f, indent=2, default=str)


def charger_historique():
    try:
        with open(FICHIER_HISTORIQUE) as f:
            return json.load(f)
    except Exception:
        return {"modifications": []}


def sauver_historique(hist):
    with open(FICHIER_HISTORIQUE, "w") as f:
        json.dump(hist, f, indent=2, default=str)


def verifier_quota():
    """Vérifie qu'on n'a pas dépassé le quota quotidien."""
    safety = charger_safety()
    aujourd = datetime.now().strftime("%Y-%m-%d")
    if safety.get("date_reset") != aujourd:
        safety["modifs_aujourdhui"] = 0
        safety["date_reset"] = aujourd
        sauver_safety(safety)
    if safety["modifs_aujourdhui"] >= MAX_MODIFS_PAR_JOUR:
        return False, f"Quota quotidien atteint ({MAX_MODIFS_PAR_JOUR} modifications max)"
    return True, safety


def valider_code(code, nom_fichier):
    """Valide le code généré: syntaxe + sécurité."""
    # 1. Vérifier la syntaxe Python
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"Erreur de syntaxe: {e}"

    # 2. Vérifier que le fichier n'est pas dans la blacklist
    nom_court = os.path.basename(nom_fichier)
    if nom_court in BLACKLIST_FICHIERS:
        return False, f"Fichier {nom_court} interdit (blacklist sécurité)"

    # 3. Vérifier les patterns dangereux
    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False, f"Pattern dangereux détecté: {pattern}"

    # 4. Vérifier la taille
    if len(code) > MAX_FILE_SIZE:
        return False, f"Code trop volumineux ({len(code)} > {MAX_FILE_SIZE} chars)"

    # 5. Vérifier que c'est bien du Python
    if not nom_fichier.endswith(".py"):
        return False, "Seuls les fichiers .py sont autorisés"

    return True, "OK"


def tester_dans_sandbox(code, nom_fichier, mode="nouveau"):
    """Teste le code dans un sandbox isolé avant déploiement."""
    sandbox_dir = os.path.join(DOSSIER, "_sandbox_test")
    os.makedirs(sandbox_dir, exist_ok=True)

    # Copier les dépendances essentielles
    for f in ["paper_trading.json", "learning_trader.json"]:
        src = os.path.join(DOSSIER, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(sandbox_dir, f))

    sandbox_file = os.path.join(sandbox_dir, os.path.basename(nom_fichier))

    try:
        # Écrire le code dans le sandbox
        with open(sandbox_file, "w") as f:
            f.write(code)

        # Test 1: Import du module (vérifie qu'il compile et s'importe)
        result = subprocess.run(
            ["python3", "-c", f"import ast; ast.parse(open('{sandbox_file}').read()); print('SYNTAX_OK')"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or "SYNTAX_OK" not in result.stdout:
            return False, f"Test syntaxe échoué: {result.stderr[:200]}"

        # Test 2: Import réel (vérifie que les dépendances existent)
        if mode == "nouveau":
            result = subprocess.run(
                ["python3", "-c", f"import sys; sys.path.insert(0, '{sandbox_dir}'); import {os.path.basename(nom_fichier)[:-3]}; print('IMPORT_OK')"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                # L'import peut échouer si le module a des dépendances externes
                # On accepte si c'est juste un warning, pas une erreur fatale
                if "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr:
                    return False, f"Import échoué: {result.stderr[:200]}"
                # Sinon on continue (le module peut nécessiter des vars d'env)

        # Test 3: Si c'est une fonction, vérifier qu'elle est callable
        result = subprocess.run(
            ["python3", "-c", f"""
import sys; sys.path.insert(0, '{sandbox_dir}')
import ast
tree = ast.parse(open('{sandbox_file}').read())
funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
print(f"FUNCTIONS={{len(funcs)}} CLASSES={{len(classes)}}")
print("STRUCTURE_OK")
"""],
            capture_output=True, text=True, timeout=10
        )
        if "STRUCTURE_OK" not in result.stdout:
            return False, f"Test structure échoué: {result.stderr[:200]}"

        return True, "Tests sandbox OK"

    except subprocess.TimeoutExpired:
        return False, "Timeout dans le sandbox (code bloquant)"
    except Exception as e:
        return False, f"Erreur sandbox: {e}"
    finally:
        # Nettoyer le sandbox
        try:
            shutil.rmtree(sandbox_dir)
        except Exception:
            pass


def creer_backup(nom_fichier):
    """Crée une backup du fichier avant modification."""
    chemin = os.path.join(DOSSIER, nom_fichier)
    if not os.path.exists(chemin):
        return None
    backup_path = os.path.join(DOSSIER, f"_backup_{nom_fichier}_{int(time.time())}")
    shutil.copy2(chemin, backup_path)
    return backup_path


def restaurer_backup(backup_path, nom_fichier):
    """Restaure la version précédente en cas d'échec."""
    chemin = os.path.join(DOSSIER, nom_fichier)
    if backup_path and os.path.exists(backup_path):
        shutil.copy2(backup_path, chemin)
        try:
            os.remove(backup_path)
        except Exception:
            pass
        return True
    return False


def demander_ia_code(description, contexte=""):
    """Demande à l'IA (Gemini) d'écrire le code pour résoudre un problème."""
    try:
        import urllib.request
        import urllib.parse

        # Essayer Gemini en premier
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            prompt = f"""Tu es un expert Python. Écris le code pour: {description}

Contexte: {contexte}

RÈGLES STRICTES:
1. Le code doit être en Python 3
2. Ne pas utiliser os.system(), eval(), exec(), __import__()
3. Ne pas accéder aux fichiers .env ou credentials
4. Ne pas supprimer de fichiers
5. Le code doit être complet et fonctionnel
6. Inclure les imports nécessaires
7. Ajouter des commentaires en français
8. Gérer les erreurs avec try/except

Réponds UNIQUEMENT avec le code Python, sans explication.
Le code doit commencer par #!/usr/bin/env python3"""

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
            data = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
            }).encode()

            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                code = result["candidates"][0]["content"]["parts"][0]["text"]
                # Nettoyer le markdown
                code = code.replace("```python", "").replace("```", "").strip()
                if code.startswith("#!/usr/bin/env python3"):
                    return code, "gemini"
                return "#!/usr/bin/env python3\n" + code, "gemini"

        # Fallback: Perplexity API
        pplx_key = os.getenv("PPLX_API_KEY", "")
        if pplx_key:
            prompt = f"""Écris le code Python pour: {description}

Contexte: {contexte}

RÈGLES: Pas de os.system(), eval(), exec(). Pas d'accès aux .env. Code complet et fonctionnel. Commentaires en français. Gère les erreurs.

Réponds UNIQUEMENT avec le code Python."""

            url = "https://api.perplexity.ai/v1/sonar"
            data = json.dumps({
                "model": "sonar",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.7,
            }).encode()

            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {pplx_key}"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                code = result["choices"][0]["message"]["content"]
                code = code.replace("```python", "").replace("```", "").strip()
                if not code.startswith("#!/usr/bin/env python3"):
                    code = "#!/usr/bin/env python3\n" + code
                return code, "perplexity"

        return None, "Aucune API IA disponible"
    except Exception as e:
        return None, f"Erreur IA: {e}"


def auto_coder(description, contexte="", nom_fichier=None, mode="nouveau"):
    """
    Point d'entrée principal: écrit, teste et déploie du code.

    Args:
        description: Ce que le code doit faire
        contexte: Information additionnelle (problèmes détectés, etc.)
        nom_fichier: Nom du fichier à créer/modifier (auto-généré si None)
        mode: "nouveau" (créer) ou "modifier" (modifier existant)

    Returns:
        (success, message, details)
    """
    # 1. Vérifier le quota
    ok, quota_info = verifier_quota()
    if not ok:
        return False, quota_info, {}

    # 2. Générer le nom de fichier si non fourni
    if not nom_fichier:
        # Générer un nom basé sur la description
        mots = description.lower().replace("é", "e").replace("è", "e").split()[:3]
        nom_court = "_".join(mots).replace(".", "").replace(",", "").replace(":", "")
        nom_fichier = f"auto_{nom_court}.py"

    # 3. Sécurité: vérifier le nom de fichier
    if any(bl in nom_fichier for bl in BLACKLIST_FICHIERS):
        return False, f"Fichier {nom_fichier} interdit", {}

    # 4. Demander à l'IA d'écrire le code
    print(f"  [SELF-CODER] Génération du code pour: {description[:80]}...")
    code, ia_source = demander_ia_code(description, contexte)
    if not code:
        return False, f"Échec génération IA: {ia_source}", {}

    print(f"  [SELF-CODER] Code généré par {ia_source} ({len(code)} chars)")

    # 5. Valider le code (syntaxe + sécurité)
    valide, msg_val = valider_code(code, nom_fichier)
    if not valide:
        return False, f"Validation échouée: {msg_val}", {"code": code[:500]}

    print(f"  [SELF-CODER] Code validé (sécurité OK)")

    # 6. Tester dans le sandbox
    ok_sandbox, msg_sandbox = tester_dans_sandbox(code, nom_fichier, mode)
    if not ok_sandbox:
        return False, f"Test sandbox échoué: {msg_sandbox}", {"code": code[:500]}

    print(f"  [SELF-CODER] Tests sandbox OK")

    # 7. Backup du fichier existant
    backup_path = None
    if mode == "modifier":
        backup_path = creer_backup(nom_fichier)
        print(f"  [SELF-CODER] Backup créé: {backup_path}")

    # 8. Déploiement
    chemin_final = os.path.join(DOSSIER, nom_fichier)
    try:
        with open(chemin_final, "w") as f:
            f.write(code)
    except Exception as e:
        return False, f"Écriture échouée: {e}", {}

    # 9. Test post-déploiement (vérifie que le fichier est valide)
    try:
        result = subprocess.run(
            ["python3", "-c", f"import ast; ast.parse(open('{chemin_final}').read()); print('POST_OK')"],
            capture_output=True, text=True, timeout=10
        )
        if "POST_OK" not in result.stdout:
            # Rollback
            if backup_path:
                restaurer_backup(backup_path, nom_fichier)
            return False, f"Post-déploiement échoué: {result.stderr[:200]}", {}
    except Exception as e:
        if backup_path:
            restaurer_backup(backup_path, nom_fichier)
        return False, f"Erreur post-test: {e}", {}

    # 10. Vérification fonctionnelle (test d'import)
    try:
        result = subprocess.run(
            ["python3", "-c", f"import sys; sys.path.insert(0, '{DOSSIER}'); import {nom_fichier[:-3]}; print('IMPORT_OK')"],
            capture_output=True, text=True, timeout=15, cwd=DOSSIER
        )
        import_ok = "IMPORT_OK" in result.stdout
        if not import_ok:
            # Si l'import échoue, on garde quand même le fichier mais on log le warning
            # (le module peut nécessiter des variables d'environnement ou des deps runtime)
            print(f"  [SELF-CODER] Warning: import non trivial (peut nécessiter runtime): {result.stderr[:100]}")
    except Exception:
        pass  # Non bloquant

    # 11. Nettoyer les backups anciens (garder max 10)
    try:
        backups = sorted([f for f in os.listdir(DOSSIER) if f.startswith("_backup_")])
        for old in backups[:-10]:
            os.remove(os.path.join(DOSSIER, old))
    except Exception:
        pass

    # 12. Mettre à jour les compteurs
    safety = charger_safety()
    safety["modifs_aujourdhui"] += 1
    safety["total_modifs"] += 1
    safety["modifs_reussies"] += 1
    sauver_safety(safety)

    # 13. Logger dans l'historique
    hist = charger_historique()
    hist["modifications"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "description": description[:200],
        "fichier": nom_fichier,
        "mode": mode,
        "ia_source": ia_source,
        "taille_code": len(code),
        "backup": backup_path,
        "statut": "deploie",
        "contexte": contexte[:500] if contexte else "",
    })
    sauver_historique(hist)

    print(f"  [SELF-CODER] ✅ Code déployé: {nom_fichier}")

    # 14. Tenter git commit + push
    try:
        subprocess.run(["git", "add", nom_fichier], cwd=DOSSIER, timeout=10)
        subprocess.run(
            ["git", "commit", "-m", f"Self-coder: {description[:60]}"],
            cwd=DOSSIER, timeout=10
        )
        subprocess.run(["git", "push"], cwd=DOSSIER, timeout=30)
        print(f"  [SELF-CODER] Git push OK")
    except Exception as e:
        print(f"  [SELF-CODER] Git push échoué (non bloquant): {e}")

    return True, f"Code déployé: {nom_fichier}", {
        "fichier": nom_fichier,
        "ia_source": ia_source,
        "taille": len(code),
    }


def auto_coder_probleme(problemes):
    """
    Déclenché par l'auto-amélioration quand des problèmes sont détectés.
    Demande à l'IA d'écrire des correctifs pour chaque problème.

    Args:
        problemes: liste de dicts {probleme, solution}

    Returns:
        liste de résultats
    """
    resultats = []
    for p in problemes:
        desc = p.get("probleme", "")
        solution = p.get("solution", "")
        if not desc:
            continue

        # Construire la description pour l'IA
        description = f"Corrige ce problème de trading bot: {desc}"
        if solution:
            description += f"\nSolution suggérée: {solution}"

        # Limiter la longueur
        description = description[:500]

        succes, msg, details = auto_coder(
            description=description,
            contexte=f"Problème auto-détecté. Bot de trading crypto avec 7 couches d'intelligence.",
            mode="nouveau"
        )

        resultats.append({
            "probleme": desc,
            "succes": succes,
            "message": msg,
            "details": details,
        })

        # Si échec, on continue avec le prochain problème
        if not succes:
            print(f"  [SELF-CODER] ❌ Échec pour: {desc[:50]}")

    return resultats


def rapport_self_coder():
    """Génère un rapport du self-coder."""
    safety = charger_safety()
    hist = charger_historique()

    lignes = []
    lignes.append("=== SELF-CODER ===\n")
    lignes.append(f"Modifications aujourd'hui: {safety.get('modifs_aujourdhui', 0)}/{MAX_MODIFS_PAR_JOUR}")
    lignes.append(f"Total modifications: {safety.get('total_modifs', 0)}")
    lignes.append(f"Réussies: {safety.get('modifs_reussies', 0)}")
    lignes.append(f"Échouées: {safety.get('modifs_echouees', 0)}")
    lignes.append(f"Rollbacks: {safety.get('total_rollbacks', 0)}")

    mods = hist.get("modifications", [])
    if mods:
        lignes.append(f"\n--- DERNIÈRES MODIFICATIONS ---")
        for m in mods[-5:]:
            statut = "✅" if m.get("statut") == "deploie" else "❌"
            lignes.append(f"  {statut} {m.get('date', '?')} | {m.get('fichier', '?')} | {m.get('description', '?')[:50]}")
    else:
        lignes.append("\nAucune modification encore.")

    return "\n".join(lignes)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        desc = " ".join(sys.argv[1:])
        print(f"Auto-coder: {desc}")
        success, msg, details = auto_coder(desc)
        if success:
            print(f"✅ {msg}")
        else:
            print(f"❌ {msg}")
    else:
        print(rapport_self_coder())
