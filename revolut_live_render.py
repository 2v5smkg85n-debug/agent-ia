#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""revolut_live_render.py — rendu de la page dashboard /live (Revolut X / bridge live).
Affiche: solde Revolut X (EUR + crypto staké), etat du pont (miroir achats/ventes),
staking, P&L reel vs capital initial (50€), et activite recente du pont.

Tout est protege par try/except — cette page ne doit JAMAIS faire planter le dashboard.
"""
import os
import json
import html
from datetime import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
MIRROR_FILE = os.path.join(DOSSIER, "revolut_mirror.json")
STAKING_LEDGER = os.path.join(DOSSIER, "staking_revolut_ledger.jsonl")

CAPITAL_INITIAL_EUR = float(os.getenv("REVOLUT_CAPITAL_INITIAL", "50"))


def _esc(s):
    try:
        return html.escape(str(s)) if s is not None else ""
    except Exception:
        return ""


def _fmt(x, dec=2):
    try:
        f = float(x)
        return f"{f:,.{dec}f}".replace(",", " ")
    except (TypeError, ValueError):
        return _esc(x)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------
# 1. Solde Revolut X
# --------------------------------------------------------------------------

def _get_balances_safe():
    """Retourne (liste_balances, erreur_str_ou_None)."""
    try:
        from revolut_x import RevolutX
    except Exception as e:
        return [], f"module revolut_x indisponible: {e}"
    try:
        client = RevolutX()
    except Exception as e:
        return [], f"client indisponible: {e}"
    try:
        raw = client.get_balances()
    except Exception as e:
        return [], f"erreur API get_balances: {e}"
    try:
        if isinstance(raw, list):
            return raw, None
        if isinstance(raw, dict):
            if "balances" in raw and isinstance(raw["balances"], list):
                return raw["balances"], None
            if "data" in raw and isinstance(raw["data"], list):
                return raw["data"], None
            return list(raw.values()), None
    except Exception as e:
        return [], f"format inattendu: {e}"
    return [], "format inattendu"


def render_balance_section():
    balances, err = _get_balances_safe()
    if err or not balances:
        msg = err or "aucun solde"
        return (
            "<h3>💰 Solde Revolut X</h3>"
            f"<p class='muted'>Données indisponibles ({_esc(msg)})</p>"
        ), None, []

    eur_available = 0.0
    staked_rows = []
    try:
        for b in balances:
            if not isinstance(b, dict):
                continue
            cur = b.get("currency") or b.get("asset") or "?"
            try:
                avail = float(b.get("available", 0) or 0)
            except (TypeError, ValueError):
                avail = 0.0
            try:
                staked = float(b.get("staked", 0) or 0)
            except (TypeError, ValueError):
                staked = 0.0
            try:
                reserved = float(b.get("reserved", 0) or 0)
            except (TypeError, ValueError):
                reserved = 0.0
            try:
                total = float(b.get("total", avail + staked + reserved) or 0)
            except (TypeError, ValueError):
                total = avail + staked + reserved
            if cur == "EUR":
                eur_available = avail
            if staked > 0:
                staked_rows.append({"currency": cur, "staked": staked, "available": avail,
                                     "reserved": reserved, "total": total})
    except Exception:
        pass

    cards = f"""
    <div class="cards">
      <div class="card"><div class="lbl">EUR disponible</div><div class="val">{_fmt(eur_available)} €</div></div>
      <div class="card"><div class="lbl">Actifs stakés</div><div class="val small">{len(staked_rows)}</div></div>
    </div>"""

    staking_tbl = ""
    if staked_rows:
        rows_html = "".join(
            f"<tr><td>{_esc(r['currency'])}</td><td>{_fmt(r['staked'], 6)}</td>"
            f"<td>{_fmt(r['available'], 6)}</td><td>{_fmt(r['total'], 6)}</td></tr>"
            for r in staked_rows
        )
        staking_tbl = f"""
        <div class='tbl-wrap'><table><thead><tr><th>Devise</th><th>Staké</th><th>Disponible</th><th>Total</th></tr></thead>
        <tbody>{rows_html}</tbody></table></div>"""
    else:
        staking_tbl = "<p class='muted'>Aucun actif staké détecté sur le compte.</p>"

    html_out = f"<h3>💰 Solde Revolut X</h3>{cards}{staking_tbl}"
    return html_out, eur_available, staked_rows


# --------------------------------------------------------------------------
# 2. Etat du pont (bridge)
# --------------------------------------------------------------------------

def render_bridge_section():
    mirror = _load_json(MIRROR_FILE, None)
    if mirror is None:
        return (
            "<h3>🌉 Pont Revolut (bridge)</h3>"
            "<p class='muted'>Données indisponibles (revolut_mirror.json introuvable)</p>"
        ), {}

    try:
        achats = mirror.get("achats", {}) if isinstance(mirror, dict) else {}
        ventes = mirror.get("ventes", []) if isinstance(mirror, dict) else []
        debut_live = mirror.get("debut_live", "jamais (dry-run)")
        live = mirror.get("live", False)
        n_achats = len(achats) if isinstance(achats, dict) else 0
        n_ventes = len(ventes) if isinstance(ventes, list) else 0
        expo = 0.0
        for v in (achats.values() if isinstance(achats, dict) else []):
            try:
                if not v.get("vendu"):
                    expo += float(v.get("montant_eur", 0) or 0)
            except Exception:
                continue
        statut_badge = "<span class='ok'>LIVE</span>" if live else "<span class='bad'>dry-run</span>"
        cards = f"""
        <div class="cards">
          <div class="card"><div class="lbl">Statut</div><div class="val small">{statut_badge}</div></div>
          <div class="card"><div class="lbl">Début live</div><div class="val small">{_esc(debut_live)}</div></div>
          <div class="card"><div class="lbl">Positions miroirées</div><div class="val">{n_achats}</div></div>
          <div class="card"><div class="lbl">Ventes réalisées</div><div class="val">{n_ventes}</div></div>
          <div class="card"><div class="lbl">Exposition totale</div><div class="val">{_fmt(expo)} €</div></div>
        </div>"""
        return f"<h3>🌉 Pont Revolut (bridge)</h3>{cards}", {
            "achats": achats, "ventes": ventes, "expo": expo, "live": live,
            "n_achats": n_achats, "n_ventes": n_ventes,
        }
    except Exception as e:
        return (
            "<h3>🌉 Pont Revolut (bridge)</h3>"
            f"<p class='muted'>Données indisponibles (erreur: {_esc(e)})</p>"
        ), {}


# --------------------------------------------------------------------------
# 3. Staking
# --------------------------------------------------------------------------

def render_staking_section():
    snap = None
    source = None
    try:
        import staking_revolut_monitor as srm
        try:
            client = srm._client()
        except Exception:
            client = None
        if client is not None:
            try:
                snap = srm.snapshot(client)
                source = "live (snapshot)"
            except Exception:
                snap = None
    except Exception:
        snap = None

    if snap is None:
        lignes = _load_jsonl(STAKING_LEDGER)
        if lignes:
            snap = lignes[-1]
            source = "ledger (dernier snapshot enregistré)"

    if not snap:
        return (
            "<h3>💎 Staking</h3>"
            "<p class='muted'>Données indisponibles (aucun snapshot staking trouvé)</p>"
        ), 0.0

    try:
        staking = snap.get("staking", {}) or {}
        eur_libre = snap.get("eur_libre", 0)
        ts = snap.get("ts", "?")
        if not staking:
            return (
                f"<h3>💎 Staking</h3>"
                f"<p class='muted'>Aucun actif staké ({_esc(source)}, {_esc(ts)}). "
                f"EUR oisif : {_fmt(eur_libre)} €</p>"
            ), 0.0
        rows_html = "".join(
            f"<tr><td>{_esc(cur)}</td><td>{_fmt(d.get('staked', 0), 6)}</td>"
            f"<td>{_fmt(d.get('total', 0), 6)}</td></tr>"
            for cur, d in staking.items() if isinstance(d, dict)
        )
        meta = f"<div class='meta'>Source: {_esc(source)} · {_esc(ts)} · EUR oisif: {_fmt(eur_libre)} €</div>"
        tbl = f"<div class='tbl-wrap'><table><thead><tr><th>Devise</th><th>Staké</th><th>Total</th></tr></thead><tbody>{rows_html}</tbody></table></div>"
        return f"<h3>💎 Staking</h3>{meta}{tbl}", 0.0
    except Exception as e:
        return (
            "<h3>💎 Staking</h3>"
            f"<p class='muted'>Données indisponibles (erreur: {_esc(e)})</p>"
        ), 0.0


# --------------------------------------------------------------------------
# 4. P&L reel
# --------------------------------------------------------------------------

def render_pnl_section(bridge_data, eur_available, staked_rows):
    try:
        ventes = bridge_data.get("ventes", []) if bridge_data else []
        gain_ventes = 0.0
        for v in ventes:
            try:
                g = v.get("gain_paper")
                if g is not None:
                    gain_ventes += float(g)
            except Exception:
                continue

        # Valeur staking approximative en EUR (best-effort, sans pricing supplementaire ici)
        staking_val_eur = 0.0
        try:
            for r in (staked_rows or []):
                # sans flux de prix dédié ici : on ne peut valoriser précisément,
                # on affiche donc la quantité stakée comme info, valeur EUR à 0 si inconnue.
                pass
        except Exception:
            pass

        expo = bridge_data.get("expo", 0.0) if bridge_data else 0.0
        eur_avail = eur_available or 0.0

        valeur_actuelle = eur_avail + expo + staking_val_eur
        pnl_eur = (valeur_actuelle + gain_ventes) - CAPITAL_INITIAL_EUR
        pnl_pct = (pnl_eur / CAPITAL_INITIAL_EUR * 100) if CAPITAL_INITIAL_EUR else 0.0

        cls = "pos" if pnl_eur >= 0 else "neg"
        cards = f"""
        <div class="cards">
          <div class="card"><div class="lbl">Capital initial</div><div class="val small">{_fmt(CAPITAL_INITIAL_EUR)} €</div></div>
          <div class="card"><div class="lbl">Gains ventes réalisées</div><div class="val small">{_fmt(gain_ventes)} €</div></div>
          <div class="card {cls}"><div class="lbl">P&amp;L réel estimé</div><div class="val">{pnl_eur:+.2f} € ({pnl_pct:+.1f}%)</div></div>
        </div>
        <p class="muted sm">Estimation = EUR disponible + exposition ouverte + gains ventes réalisées − capital initial. Valeur staking non incluse (pricing non disponible sur cette page).</p>"""
        return f"<h3>📊 P&amp;L réel</h3>{cards}"
    except Exception as e:
        return f"<h3>📊 P&amp;L réel</h3><p class='muted'>Données indisponibles (erreur: {_esc(e)})</p>"


# --------------------------------------------------------------------------
# 5. Activite recente du pont
# --------------------------------------------------------------------------

def render_recent_activity(bridge_data):
    try:
        ventes = bridge_data.get("ventes", []) if bridge_data else []
        if not ventes:
            return "<h3>🕓 Activité récente du pont</h3><p class='muted'>Aucune vente miroirée pour l'instant</p>"
        recent = list(ventes)[-5:]
        recent.reverse()
        rows_html = ""
        for v in recent:
            try:
                symbole = _esc(v.get("symbole", "?"))
                paire = _esc(v.get("paire", "?"))
                montant = _fmt(v.get("montant_eur", 0))
                gain = v.get("gain_paper")
                gain_str = f"{float(gain):+.2f} €" if gain is not None else "?"
                date_vente = _esc(v.get("date_vente", v.get("date_miroir", "?")))
                rows_html += (
                    f"<tr><td>{date_vente}</td><td>{symbole}</td><td>{paire}</td>"
                    f"<td>{montant} €</td><td>{gain_str}</td></tr>"
                )
            except Exception:
                continue
        tbl = (
            "<div class='tbl-wrap'><table><thead><tr><th>Date vente</th><th>Symbole</th>"
            "<th>Paire</th><th>Montant</th><th>Gain paper</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        return f"<h3>🕓 Activité récente du pont</h3>{tbl}"
    except Exception as e:
        return f"<h3>🕓 Activité récente du pont</h3><p class='muted'>Données indisponibles (erreur: {_esc(e)})</p>"


# --------------------------------------------------------------------------
# Page complete
# --------------------------------------------------------------------------

def render_live(token):
    """Construit la page /live. Ne doit JAMAIS lever d'exception."""
    try:
        balance_html, eur_available, staked_rows = render_balance_section()
    except Exception as e:
        balance_html = f"<h3>💰 Solde Revolut X</h3><p class='muted'>Données indisponibles ({_esc(e)})</p>"
        eur_available, staked_rows = 0.0, []

    try:
        bridge_html, bridge_data = render_bridge_section()
    except Exception as e:
        bridge_html = f"<h3>🌉 Pont Revolut (bridge)</h3><p class='muted'>Données indisponibles ({_esc(e)})</p>"
        bridge_data = {}

    try:
        staking_html, _ = render_staking_section()
    except Exception as e:
        staking_html = f"<h3>💎 Staking</h3><p class='muted'>Données indisponibles ({_esc(e)})</p>"

    try:
        pnl_html = render_pnl_section(bridge_data, eur_available, staked_rows)
    except Exception as e:
        pnl_html = f"<h3>📊 P&amp;L réel</h3><p class='muted'>Données indisponibles ({_esc(e)})</p>"

    try:
        activity_html = render_recent_activity(bridge_data)
    except Exception as e:
        activity_html = f"<h3>🕓 Activité récente du pont</h3><p class='muted'>Données indisponibles ({_esc(e)})</p>"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tok = _esc(token)

    try:
        return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent IA — Revolut Live</title>
<meta http-equiv="refresh" content="60">
<style>
:root{{--bg:#0d1117;--card:#161b22;--txt:#e6edf3;--muted:#8b949e;--pos:#4ade80;--neg:#f87171;--border:#30363d}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0 auto;padding:14px;max-width:760px}}
h1{{font-size:19px;margin:6px 0 2px}}
h3{{font-size:14px;margin:18px 0 8px;border-bottom:1px solid var(--border);padding-bottom:4px}}
.count{{color:var(--muted);font-size:12px}}
.muted{{color:var(--muted);font-size:13px}}
.sm{{font-size:11px}}
.meta{{color:var(--muted);font-size:12px;margin-bottom:4px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:9px}}
.card .lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
.card .val{{font-size:17px;font-weight:600;margin-top:2px}}
.card.pos .val{{color:var(--pos)}}
.card.neg .val{{color:var(--neg)}}
.card .val.small{{font-size:15px}}
.card .sub{{font-size:10px;color:var(--muted);margin-top:2px}}
.ok{{color:var(--pos);font-weight:600}}
.bad{{color:var(--neg);font-weight:600}}
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px}}
th,td{{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}
th{{color:var(--muted);font-weight:600;font-size:11px}}
.lnk{{color:#58a6ff;text-decoration:none}}
</style></head><body>
<h1>Agent IA — Revolut Live</h1>
<div class="meta">Actualisation auto 60s · {now} ·
<a class="lnk" href="/?token={tok}">📈 Paper Trading</a> ·
<a class="lnk" href="/perf?token={tok}">📊 Performance</a> ·
<a class="lnk" href="/ia?token={tok}">🧠 IA</a></div>
{balance_html}
{bridge_html}
{staking_html}
{pnl_html}
{activity_html}
<div class="meta" style="margin-top:16px">Données live depuis Revolut X (API), revolut_mirror.json et staking_revolut_ledger.jsonl</div>
</body></html>"""
    except Exception as e:
        return (
            "<html><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:20px'>"
            f"<h2>Erreur page Live</h2><pre>{_esc(e)}</pre></body></html>"
        )
