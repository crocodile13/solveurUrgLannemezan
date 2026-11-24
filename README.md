# Solveur de planning des urgences (CP-SAT)

## Installation
    pip install ortools openpyxl

## Fichiers
- `planning_solver.py` : le solveur. Il lit le classeur (cases rouges = créneaux déjà pris par le chef,
  colonne COURS, colonne CONGÉS, fériés, tarifs BILAN!L8:L11, mois précédents = historique) et écrit
  les noms en couleur dans les mois demandés.
- `donnees/planning_base.xlsx` : classeur de départ (novembre rempli, décembre→avril vides).
- `donnees/unav.json` : jours où quelqu'un ne peut pas travailler (règle dure). Noël Marien, nouvel an Quentin.
- `donnees/soft.json` : jours où on préfère ne pas travailler (pénalité, `--w-soft-off`).
- `donnees/conges3.json` : congés (comptés à la densité moyenne du mois, pas comme postes faits).
- `donnees/force2.json` : créneaux imposés (`"2026-12-25M": "YAZID"` ; M = 9h-19h, E = 13h-23h).
- `outils/check.py fichier.json` : contrôles (E->M interdit, 5 j/7, séries, médianes, €).
- `outils/st.py`, `outils/cal13.py` : week-ends libres, ponts jeudi→lundi, calendrier texte.

## Commande type (réglages « top », décembre-janvier puis février)
    python3 planning_solver.py donnees/planning_base.xlsx sortie.xlsx \
      --months "DEC 26" "JANV 27" --time 300 --workers 2 --json-out sortie.json \
      --unavail donnees/unav.json --conges donnees/conges3.json --soft-off donnees/soft.json \
      --force donnees/force2.json --max-month-range 2 --w-start 120 --w-iso 300 --w-rest1 300

    # puis février par-dessus (décembre-janvier deviennent l'historique)
    python3 planning_solver.py sortie.xlsx sortie_fev.xlsx --months "FEV 27" --time 300 \
      --json-out fev.json --unavail donnees/unav.json --soft-off donnees/soft.json \
      --max-month-range 2 --w-start 120 --w-iso 300 --w-rest1 300

## Options utiles
- `--we-light QUENTIN:1 MARIEN:0.3 --w-we 300 --w-we-day 75` : moins de week-ends pour ces personnes.
- `--pay-exclude QUENTIN` : sort cette personne de l'équilibre des € (pas de compensation).
- `--long-off MARIEN --long-min 2` : ponts jeudi→lundi libres.
- `--w-wrun "2:300,3:100"` / `--w-frun "2:250"` : pénalise les blocs travaillés / libres de 2-3 jours.
- `--we-bal MARIEN,YAZID --we-bal-max 2` : même nombre de jours de week-end à 2 près.
- `--hint ancien.json` : repartir d'une solution existante.
- Calcul en 2 temps (déc-janv puis fév) : bien meilleur que les 3 mois d'un coup.
