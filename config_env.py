"""config_env — lit un reglage dans l'environnement du processus, sinon dans ~/agent-ia/.env.
Pourquoi : les services systemd ne chargent pas toujours .env ; sans ceci, un reglage ajoute dans .env
(LLM_LIBRE=0, CRITIQUE_MODE=malus, PORTE_CUSUM=0, REVENUS_PARALLELES=0...) pouvait rester sans effet."""
import os
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
_CACHE = {"t": 0.0, "d": {}}


def _env_fichier():
    now = time.time()
    if now - _CACHE["t"] > 30:
        d = {}
        try:
            with open(os.path.join(DOSSIER, ".env")) as f:
                for line in f:
                    s = line.strip()
                    if "=" in s and not s.startswith("#"):
                        k, v = s.split("=", 1)
                        d[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
        _CACHE["t"], _CACHE["d"] = now, d
    return _CACHE["d"]


def lire(nom, defaut=None):
    v = os.getenv(nom)
    if v is not None and v != "":
        return v
    return _env_fichier().get(nom, defaut)
