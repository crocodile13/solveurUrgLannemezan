#!/usr/bin/env python3
"""Planning des internes — solveur CP-SAT (OR-Tools).

Lit directement le classeur (cases rouges, cours, fériés, tarifs, historique déjà
rempli), planifie les mois demandés et réécrit les noms dans le classeur.

Exemple :
    python3 planning_solver.py IN.xlsx OUT.xlsx --months "DEC 26" "JANV 27" "FEV 27" \
        --time 60 --hint ancien.json --unavail unavail.json

unavail.json (facultatif) : {"MARIEN": ["2026-12-24", "2026-12-25"], ...}
"""
import argparse, datetime as dt, json, re, statistics, time
from collections import Counter
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from ortools.sat.python import cp_model

PEOPLE = ["MARIEN", "QUENTIN", "YAZID"]
COL = {"MARIEN": "BDD7EE", "QUENTIN": "C6EFCE", "YAZID": "FCE4D6"}
DARK = {"MARIEN": "1F4E79", "QUENTIN": "375623", "YAZID": "833C0B"}
MONTHS = {"NOV": 11, "DEC": 12, "JANV": 1, "FEV": 2, "MARS": 3, "AVR": 4}
FERIES = {dt.date(2026, 11, 11), dt.date(2026, 12, 25), dt.date(2027, 1, 1), dt.date(2027, 3, 29)}
RED = ("FFFF0000", "00FF0000")
ONE = dt.timedelta(days=1)


def sheet_month(name):
    m, y = name.split()
    return 2000 + int(y), MONTHS[m]


def is_red(cell):
    try:
        return cell.fill.fill_type is not None and cell.fill.fgColor.rgb in RED
    except Exception:
        return False


def read_workbook(path, plan_sheets):
    """Renvoie slots ouverts, infos par jour, historique (affectations déjà faites) et tarifs."""
    wb = openpyxl.load_workbook(path)
    b = wb["BILAN"]
    rates = {"demi_sem": b["L8"].value, "demi_sam": b["L9"].value,
             "garde_sam": b["L10"].value, "garde_dim": b["L11"].value}
    slots, info, hist = [], {}, {}
    for name in wb.sheetnames:
        if name in ("BILAN", "RÈGLES"):
            continue
        y, mo = sheet_month(name)
        ws = wb[name]
        hdr = {str(ws.cell(1, c).value or "").strip(): c for c in range(1, ws.max_column + 1)}
        c_cours, c_dbl = hdr.get("COURS", 6), hdr.get("2e en 9h-19h", 15)
        for r in range(2, ws.max_row + 1):
            d = ws.cell(r, 2).value
            if not isinstance(d, int):
                continue
            day = dt.date(y, mo, d)
            cours = str(ws.cell(r, c_cours).value or "")
            dbl = ws.cell(r, c_dbl).value == 1  # « 2e en 9h-19h » (début de stage)
            info[day] = {"full": cours.startswith("JOURNÉE – TOUS"), "half": cours.startswith("½"),
                         "sheet": name, "row": r}
            for c, s in ((3, "M"), (4, "E")):
                cell = ws.cell(r, c)
                if name in plan_sheets:
                    if not info[day]["full"] and not is_red(cell):
                        slots.append((day, s))
                    continue
                for p in PEOPLE:  # historique
                    if p in str(cell.value or "").upper():
                        hist[(p, day)] = "M" if dbl else s
    return wb, rates, slots, info, hist


def pay(rates, day, s):
    """Montant en centimes."""
    w = day.weekday()
    if w == 6 or day in FERIES:
        v = rates["garde_dim"]
    elif w == 5:
        v = rates["garde_sam"] if s == "E" else rates["demi_sam"]
    else:
        v = rates["demi_sem"] if s == "E" else 0
    return int(round(v * 100))


def solve(args):
    t0 = time.time()
    wb, rates, slots, info, hist = read_workbook(args.input, set(args.months))
    days = sorted({d for d, _ in slots} | {d for d, i in info.items() if i["sheet"] in args.months})
    d0, d1 = days[0], days[-1]
    S = set(slots)
    unavail = json.load(open(args.unavail)) if args.unavail else {}
    conges = json.load(open(args.conges)) if args.conges else {}      # interdits + comptés comme jours faits
    soft_off = json.load(open(args.soft_off)) if args.soft_off else {}  # repos souhaités (pénalisés si travaillés)
    for p, ds in conges.items():
        unavail.setdefault(p, []).extend(ds)
    credit = {p: Counter(dt.date.fromisoformat(d).month for d in conges.get(p, [])) for p in PEOPLE}
    m = cp_model.CpModel()

    x = {(p, d, s): m.NewBoolVar(f"x_{p}_{d}_{s}") for p in PEOPLE for (d, s) in slots}
    for d, s in slots:
        m.AddExactlyOne(x[p, d, s] for p in PEOPLE)

    # work[p,d] : constante (historique / hors période) ou variable booléenne
    work = {}
    for p in PEOPLE:
        for d in days:
            vs = [x[p, d, s] for s in "ME" if (d, s) in S]
            if not vs:
                work[p, d] = 0
            else:
                w = m.NewBoolVar(f"w_{p}_{d}")
                m.Add(w == sum(vs))  # implique au plus 1 poste par jour
                work[p, d] = w
            if d.isoformat() in unavail.get(p, []):
                for v in vs:
                    m.Add(v == 0)

    def W(p, d):
        if d < d0:
            return 1 if (p, d) in hist else 0
        return work.get((p, d), 0)

    def busy(p, d):  # travail ou cours journée entière
        if d in info and info[d]["full"] and d >= d0:
            return 1
        return W(p, d)

    span = [d0 - ONE * 6 + ONE * i for i in range((d1 - d0).days + 7)]
    for p in PEOPLE:
        # repos de sécurité : pas de 13h-23h suivi d'un 9h-19h
        prev_e = 1 if hist.get((p, d0 - ONE)) == "E" else 0
        if prev_e and (d0, "M") in S:
            m.Add(x[p, d0, "M"] == 0)
        for d in days:
            if (d, "E") in S and (d + ONE, "M") in S:
                m.AddBoolOr([x[p, d, "E"].Not(), x[p, d + ONE, "M"].Not()])
        for i in range(len(span)):
            for k, lim in ((args.max_consec + 1, args.max_consec), (7, 5)):
                win = span[i:i + k]
                if len(win) == k and win[-1] >= d0:
                    m.Add(sum(W(p, d) for d in win) <= lim)

    # --- objectif (entier : 10 points par centime, 1000 points par unité de poids) ---
    def rng(exprs, name, ub):
        hi, lo = m.NewIntVar(0, ub, f"hi_{name}"), m.NewIntVar(0, ub, f"lo_{name}")
        for e in exprs:
            m.Add(e <= hi)
            m.Add(e >= lo)
        return hi - lo

    # Congés : on fait « comme s'ils n'existaient pas » pour la densité du mois.
    # Mois par mois, postes et gardes sont comparés à densité égale (valeur × jours du mois / jours disponibles),
    # donc pas de rattrapage forcé dans le même mois ; au cumul, chaque jour de congé compte pour la densité
    # moyenne de postes du mois (et non pour un poste entier).
    mdays = Counter(d.month for d in days)
    mslots = Counter(d.month for d, _ in slots)
    dens = {mo: mslots[mo] / (len(PEOPLE) * mdays[mo]) for mo in mdays}
    credit10 = {p: round(10 * sum(dens.get(mo, 0) * n for mo, n in credit[p].items())) for p in PEOPLE}
    fac = {(p, mo): round(100 * mdays[mo] / max(1, mdays[mo] - credit[p][mo])) for p in PEOPLE for mo in mdays}

    hist_pay = {p: sum(pay(rates, d, s) for (q, d), s in hist.items() if q == p) for p in PEOPLE}
    hist_n = {p: sum(1 for (q, _) in hist if q == p) for p in PEOPLE}
    hist_e = {p: sum(1 for (q, _), s in hist.items() if q == p and s == "E") for p in PEOPLE}
    UB = 10 ** 9
    cum_pay = [hist_pay[p] + sum(pay(rates, d, s) * x[p, d, s] for d, s in slots) for p in PEOPLE]
    cum_n10 = [10 * hist_n[p] + credit10[p] + sum(10 * x[p, d, s] for d, s in slots) for p in PEOPLE]
    cum_e = [hist_e[p] + sum(x[p, d, "E"] for d, s in slots if s == "E") for p in PEOPLE]
    # --pay-exclude : ces personnes sortent de l'équilibre des gardes (€) ; on équilibre alors
    # les 13h-23h de semaine (hors WE/fériés) pour tous, sans compensation des week-ends refusés
    excl = {q.upper() for q in (args.pay_exclude or [])}
    keep = [i for i, p in enumerate(PEOPLE) if p not in excl]
    if excl:
        wk = lambda d: d.weekday() < 5 and d not in FERIES
        cum_e = [sum(1 for (q, d), s in hist.items() if q == p and s == "E" and wk(d))
                 + sum(x[p, d, "E"] for d, s in slots if s == "E" and wk(d)) for p in PEOPLE]
        cum_pay = [cum_pay[i] for i in keep]
    terms = [int(10*args.w_cum_eur) * rng(cum_pay, "cpay", UB),          # centimes
             int(100*args.w_cum_posts) * rng(cum_n10, "cn", 4000),      # dixièmes de poste
             int(1000*args.w_cum_eve) * rng(cum_e, "ce", 400)]
    for mo in sorted(mdays):
        ms = [(d, s) for d, s in slots if d.month == mo]
        pay_n = [fac[p, mo] * sum(round(pay(rates, d, s) / 100) * x[p, d, s] for d, s in ms) for p in PEOPLE]   # € ×100 ≈ centimes
        posts_n = [fac[p, mo] * sum(x[p, d, s] for d, s in ms) for p in PEOPLE]                    # ×100
        terms.append(int(10*args.w_month_eur) * rng([pay_n[i] for i in keep], f"mp{mo}", UB))
        terms.append(int(10*args.w_month_posts) * rng(posts_n, f"mn{mo}", 10000))
        if args.max_month_range is not None:
            for i in range(len(PEOPLE)):
                for j in range(len(PEOPLE)):
                    if i != j:
                        m.Add(posts_n[i] - posts_n[j] <= 100 * args.max_month_range + 99)

    # repos d'1 jour / 2 jours, jour de travail isolé (booléens, indicateurs exacts)
    pen = []
    for p in PEOPLE:
        for d in days:
            b_prev, b, b_next = busy(p, d - ONE), busy(p, d), busy(p, d + ONE) if d < d1 else 1
            f1 = m.NewBoolVar("")
            m.Add(f1 >= b_prev + b_next - b - 1)
            pen.append(int(1000*args.w_rest1) * f1)
            if d < d1:
                b_next2 = busy(p, d + 2 * ONE) if d + ONE < d1 else 1
                f2 = m.NewBoolVar("")
                m.Add(f2 >= b_prev + b_next2 - b - b_next - 1)
                pen.append(int(1000*args.w_rest2) * f2)
            st = m.NewBoolVar("")                       # début de bloc de travail
            m.Add(st >= W(p, d) - W(p, d - ONE))
            pen.append(int(1000 * args.w_start) * st)
            iso = m.NewBoolVar("")
            m.Add(iso >= W(p, d) - b_prev - b_next)
            pen.append(int(1000*args.w_iso) * iso)
    for k, p in (json.load(open(args.force)) if args.force else {}).items():  # affectations imposées
        d, sl = dt.date.fromisoformat(k[:-1]), k[-1]
        m.Add(x[p.upper(), d, sl] == 1)
    for p, ds in soft_off.items():
        for d in ds:
            d = dt.date.fromisoformat(d)
            if (p, d) in work and not isinstance(work[p, d], int):
                pen.append(int(1000 * args.w_soft_off) * work[p, d])
    # week-ends : pour les personnes listées, pénalité par week-end touché (sam ou dim travaillé) + par jour de WE
    wec = {}
    for q in (args.we_light or []):
        p, _, f = q.upper().partition(":")
        f = float(f) if f else 1.0
        for d in days:
            if d.weekday() == 5:
                wd = [work.get((p, d + ONE * k), 0) for k in (0, 1)]
                wv = [v for v in wd if not isinstance(v, int)]
                if not wv:
                    continue
                t = m.NewBoolVar("")
                for v in wv:
                    m.Add(t >= v)
                pen.append(int(1000 * args.w_we * f) * t)
                wec.setdefault(p, []).extend(wv)
                pen.extend(int(1000 * args.w_we_day * f) * v for v in wv)
    # blocs de travail de 2 jours (on préfère 3-4)
    if args.w_blk2:
        for p in PEOPLE:
            for d in days:
                if d + ONE > d1:
                    continue
                b2 = m.NewBoolVar("")
                m.Add(b2 >= busy(p, d) + busy(p, d + ONE) - busy(p, d - ONE)
                      - (busy(p, d + 2 * ONE) if d + 2 * ONE <= d1 else 1) - 1)
                pen.append(int(1000 * args.w_blk2) * b2)
    # pénalités génériques par longueur exacte de bloc : --w-wrun "2:200,3:50" (travail), --w-frun (libre)
    def parse(sp):
        return {int(a): float(b) for a, b in (t.split(":") for t in sp.split(","))} if sp else {}
    for kind, spec in (("w", parse(args.w_wrun)), ("f", parse(args.w_frun))):
        for L, wt in spec.items():
            for p in PEOPLE:
                for d in days:
                    if d + L * ONE > d1:
                        continue
                    inside = [busy(p, d + k * ONE) for k in range(L)]
                    edge = [busy(p, d - ONE), busy(p, d + L * ONE)]
                    if kind == "w":
                        expr = sum(inside) - sum(edge) - L + 1
                    else:
                        expr = sum(edge) - sum(inside) - 1
                    if isinstance(expr, int):
                        if expr >= 1:
                            pen.append(int(1000 * wt))
                        continue
                    b = m.NewBoolVar("")
                    m.Add(b >= expr)
                    pen.append(int(1000 * wt) * b)
    # longs week-ends jeudi -> lundi libres (retour le mardi), bonus
    nlong = {}
    for p in [q.upper() for q in (args.long_off or [])]:
        for d in days:
            if d.weekday() != 3 or d + 4 * ONE > d1:
                continue
            bs = [busy(p, d + k * ONE) for k in range(5)]
            if any(isinstance(b, int) and b == 1 for b in bs):
                continue
            lo = m.NewBoolVar("")
            for b in bs:
                if not isinstance(b, int):
                    m.Add(lo <= 1 - b)
            pen.append(-int(1000 * args.w_long) * lo)
            nlong.setdefault(p, []).append(lo)
    if args.long_min is not None:
        for p, vs in nlong.items():
            m.Add(sum(vs) >= args.long_min)
    if args.we_bal:
        grp = [q.upper() for q in args.we_bal.split(",")]
        wd = {p: sum(work.get((p, d), 0) for d in days if d.weekday() >= 5) for p in grp}
        for a_ in grp:
            for b_ in grp:
                if a_ != b_:
                    m.Add(wd[a_] - wd[b_] <= args.we_bal_max)
    if args.we_max is not None:
        first = args.we_light[0].upper().partition(":")[0]   # plafond : 1re personne de --we-light seulement
        m.Add(sum(wec.get(first, [])) <= args.we_max)
    m.Minimize(sum(terms) + sum(pen))

    if args.hint:
        h = json.load(open(args.hint))
        for (p, d, s), v in x.items():
            m.AddHint(v, 1 if h.get(f"{d.isoformat()}{s}", "").upper() == p else 0)

    def run(seconds, seed):
        sv = cp_model.CpSolver()
        sv.parameters.max_time_in_seconds = seconds
        sv.parameters.num_workers = args.workers
        sv.parameters.log_search_progress = args.log
        sv.parameters.linearization_level = args.lin
        sv.parameters.random_seed = seed
        return sv, sv.Solve(m)

    # passe principale puis « polissage » : on relance en partant de la meilleure solution
    # (indice + borne supérieure stricte sur l'objectif), avec une graine différente à chaque fois
    solver, st = run(args.time, args.seed or 0)
    best = solver.ObjectiveValue()
    vals = {k: solver.Value(v) for k, v in x.items()}
    for i in range(args.polish):
        m.ClearHints()
        for k, v in x.items():
            m.AddHint(v, vals[k])
        sv, st2 = run(args.polish_time, (args.seed or 0) + i + 1)
        if st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) and sv.ObjectiveValue() < best:
            best = sv.ObjectiveValue(); vals = {k: sv.Value(v) for k, v in x.items()}; solver, st = sv, st2
        print(f"  polissage {i + 1}/{args.polish} : objectif {best:.0f}")
    print(f"statut {solver.StatusName(st)}  objectif {best:.0f}  borne {solver.BestObjectiveBound():.0f}  "
          f"temps {time.time() - t0:.1f}s")
    res = {f"{d.isoformat()}{s}": p.capitalize() for (p, d, s) in x if vals[p, d, s]}
    json.dump(res, open(args.json_out, "w"))

    # écriture dans le classeur
    for (d, s) in slots:
        p = res[f"{d.isoformat()}{s}"].upper()
        ws = wb[info[d]["sheet"]]
        cell = ws.cell(info[d]["row"], 3 if s == "M" else 4)
        cell.value = p + (" (COURS)" if info[d]["half"] else "")
        cell.fill = PatternFill("solid", fgColor=COL[p])
        cell.font = Font(name="Arial", bold=True, color=DARK[p])
        cell.alignment = Alignment(horizontal="center")
    wb.save(args.output)
    report(res, info, days, hist, rates)


def report(res, info, days, hist, rates):
    for P in PEOPLE:
        p = P.capitalize()
        sh = {dt.date.fromisoformat(k[:-1]): k[-1] for k, v in res.items() if v == p}
        busy = set(sh) | {d for d in days if info[d]["full"]}
        free, c = [], 0
        for d in days:
            if d not in busy:
                c += 1
            elif c:
                free.append(c); c = 0
        if c:
            free.append(c)
        allw = set(sh) | {d for (q, d) in hist if q == P}
        mx = c = 0
        for d in sorted(allw):
            c = c + 1 if d - ONE in allw else 1
            mx = max(mx, c)
        eur = sum(pay(rates, d, s) for d, s in sh.items()) / 100
        per = Counter(d.month for d in sh)
        print(f"{P:8} postes {dict(per)}  gardes {eur:8.2f} €  libres méd {statistics.median(free)} "
              f"repos 1 j {free.count(1)}  max consécutif {mx}")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("input"); a.add_argument("output")
    a.add_argument("--months", nargs="+", required=True)
    a.add_argument("--json-out", default="solution.json")
    a.add_argument("--hint"); a.add_argument("--unavail"); a.add_argument("--conges"); a.add_argument("--soft-off")
    a.add_argument("--w-soft-off", type=float, default=300)
    a.add_argument("--max-month-range", type=int)
    a.add_argument("--w-start", type=float, default=0)
    a.add_argument("--force")
    a.add_argument("--we-light", nargs="*")
    a.add_argument("--pay-exclude", nargs="*")
    a.add_argument("--we-max", type=int)
    a.add_argument("--w-blk2", type=float, default=0)
    a.add_argument("--long-off", nargs="*")
    a.add_argument("--w-long", type=float, default=500)
    a.add_argument("--long-min", type=int)
    a.add_argument("--w-wrun"); a.add_argument("--w-frun")
    a.add_argument("--we-bal"); a.add_argument("--we-bal-max", type=int, default=2)
    a.add_argument("--w-we", type=float, default=400)
    a.add_argument("--w-we-day", type=float, default=100)
    a.add_argument("--time", type=float, default=60)
    a.add_argument("--workers", type=int, default=2)
    a.add_argument("--max-consec", type=int, default=4)
    a.add_argument("--w-cum-eur", type=float, default=1)      # par centime d'écart cumulé
    a.add_argument("--w-month-eur", type=float, default=0.3)  # par centime d'écart mensuel
    a.add_argument("--w-cum-posts", type=float, default=60)   # par poste d'écart (×100)
    a.add_argument("--w-month-posts", type=float, default=60)
    a.add_argument("--w-cum-eve", type=float, default=40)
    a.add_argument("--w-rest1", type=float, default=200)
    a.add_argument("--w-rest2", type=float, default=60)
    a.add_argument("--w-iso", type=float, default=100)
    a.add_argument("--log", action="store_true")
    a.add_argument("--lin", type=int, default=2)
    a.add_argument("--seed", type=int)
    a.add_argument("--polish", type=int, default=0)
    a.add_argument("--polish-time", type=float, default=30)
    solve(a.parse_args())
