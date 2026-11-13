#!/usr/bin/env bash
# Suivi de prospection — tient sur une ligne depuis l'iPhone.
#   bash revenus/prospection.sh ajouter A "Nodva" mail        -> note l'envoi, relance prévue à J+4
#   bash revenus/prospection.sh reponse "Nodva" "ok rdv mardi" -> note une réponse (statut repondu)
#   bash revenus/prospection.sh relances                       -> contacts à relancer aujourd'hui ou avant
#   bash revenus/prospection.sh liste                          -> tout le fichier
# Fichier : revenus/donnees/prospection.csv  (date;groupe;contact;canal;statut;reponse;relance)
set -e
ICI="$(cd "$(dirname "$0")" && pwd)"
F="$ICI/donnees/prospection.csv"
mkdir -p "$ICI/donnees"
[ -f "$F" ] || echo "date;groupe;contact;canal;statut;reponse;relance" > "$F"
# le clavier iPhone colle parfois une espace insécable : on ne garde que les lettres
cmd=$(printf %s "${1:-liste}" | tr -cd "a-z")
[ -n "$cmd" ] || cmd=liste
case "$cmd" in
  ajouter)
    [ -n "${3:-}" ] || { echo "usage: ajouter GROUPE CONTACT [CANAL]"; exit 1; }
    echo "$(date +%F);$2;$3;${4:-mail};envoye;;$(date -d '+4 days' +%F)" >> "$F"
    echo "noté : $3 (relance le $(date -d '+4 days' +%F))" ;;
  reponse)
    [ -n "${2:-}" ] || { echo "usage: reponse CONTACT TEXTE"; exit 1; }
    python3 - "$F" "$2" "${3:-}" <<'PY'
import sys,csv
f,qui,txt=sys.argv[1],sys.argv[2].lower(),sys.argv[3]
rows=list(csv.reader(open(f,encoding="utf-8"),delimiter=";"))
n=0
for r in rows[1:]:
    if len(r)>=7 and r[2].lower()==qui:
        r[4]="repondu"; r[5]=txt; r[6]=""; n+=1
csv.writer(open(f,"w",encoding="utf-8",newline=""),delimiter=";",lineterminator="\n").writerows(rows)
print(f"{n} ligne(s) mise(s) à jour")
PY
    ;;
  relances)
    auj=$(date +%F)
    awk -F';' -v d="$auj" 'NR>1 && $5=="envoye" && $7!="" && $7<=d {print "à relancer : "$3" ("$2", envoyé le "$1", "$4")"}' "$F"
    ;;
  liste) column -s';' -t "$F" 2>/dev/null || cat "$F" ;;
  *) echo "commandes : ajouter | reponse | relances | liste"; exit 1 ;;
esac
