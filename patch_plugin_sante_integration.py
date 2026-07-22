#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_plugin_sante_integration.py — Wrap les hooks de plugins avec
plugin_sante.record() pour tracker allow/veto/error par plugin. Permet à
verifier() (cron horaire) de désactiver auto les plugins défaillants."""
import sys

f = "paper_trading.py"
p = open(f, encoding="utf-8").read()
ok = True

# Edit 1: hook_entree — record allow/veto/error
A1 = '''                        _allow, _raison = _mod.hook_entree(pf, signal)
                        if not _allow:
                            print(f"  [PLUGIN {_fn}] entrée bloquée: {_raison}")
                            return False
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_entree erreur: {_e}")'''
B1 = '''                        _allow, _raison = _mod.hook_entree(pf, signal)
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "veto" if not _allow else "allow")
                        except Exception:
                            pass
                        if not _allow:
                            print(f"  [PLUGIN {_fn}] entrée bloquée: {_raison}")
                            return False
                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_entree erreur: {_e}")
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "error")
                        except Exception:
                            pass'''

# Edit 2: hook_sizing — record error
A2 = '''                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_sizing erreur: {_e}")
        except Exception:
            pass
    # Clamp de sécurité: un plugin bugué ne peut pas dépasser le liquide ni aller négatif'''
B2 = '''                    except Exception as _e:
                        print(f"  [PLUGIN {_fn}] hook_sizing erreur: {_e}")
                        try:
                            from plugin_sante import record as _ps_rec
                            _ps_rec(_fn, "error")
                        except Exception:
                            pass
        except Exception:
            pass
    # Clamp de sécurité: un plugin bugué ne peut pas dépasser le liquide ni aller négatif'''

if "plugin_sante import record" in p:
    print("[paper] plugin_sante déjà intégré - skip"); sys.exit(0)
if A1 in p:
    p = p.replace(A1, B1, 1); print("[paper] edit1: record hook_entree")
else:
    print("[paper] ERREUR ancre edit1"); ok = False
if A2 in p:
    p = p.replace(A2, B2, 1); print("[paper] edit2: record hook_sizing erreur")
else:
    print("[paper] ERREUR ancre edit2"); ok = False
if not ok:
    sys.exit(1)
open(f, "w", encoding="utf-8").write(p)
print("\n=== PLUGIN SANTÉ INTÉGRÉ ===")
print("Compteurs allow/veto/error par plugin -> auto-rollback si défaillant")
