#!/usr/bin/env python3
"""
validation_stats.py — outils statistiques pur Python (pas de numpy) pour ne plus se raconter d'histoires.

  - beta_posterior(g, n, a0=5, b0=5) : moyenne et intervalle de credibilite 90 % d'un taux de reussite (prior Beta(5,5))
  - echantillon_beta(a, b)           : tirage Thompson (allocation de taille entre strategies)
  - point_mort(gain_moyen, perte_moyenne) : WR minimum pour une esperance nulle
  - sharpe_deflate(sharpe, n_trades, n_essais, skew, kurt) : Deflated Sharpe Ratio (Bailey & Lopez de Prado)
  - trades_minimum(wr, ratio, confiance) : nombre de trades necessaires pour distinguer la strategie du hasard
  - monte_carlo(gains, n=2000) : distribution du drawdown et du P&L par bootstrap des trades
  - valider_strategie(gains, n_essais=1) : verdict unique utilise par le registre / l'auto-evolution
"""
import math
import random


# ------------------------------------------------------------------ fonction beta incomplete (Numerical Recipes)
def _betacf(a, b, x):
    MAXIT, EPS, FPMIN = 200, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c; c = c if abs(c) > FPMIN else FPMIN
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > FPMIN else FPMIN)
        c = 1.0 + aa / c; c = c if abs(c) > FPMIN else FPMIN
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def beta_cdf(x, a, b):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    bt = math.exp(lbeta)
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def beta_ppf(p, a, b):
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def beta_posterior(g, n, a0=5.0, b0=5.0, niveau=0.90):
    """Taux de reussite bayesien. g gagnants sur n trades, prior Beta(a0,b0) = 'je pense 50 %, poids 10 trades'."""
    a, b = a0 + g, b0 + (n - g)
    q = (1 - niveau) / 2
    return {"a": a, "b": b, "moyenne": round(a / (a + b) * 100, 1),
            "ic_bas": round(beta_ppf(q, a, b) * 100, 1), "ic_haut": round(beta_ppf(1 - q, a, b) * 100, 1)}


def echantillon_beta(a, b):
    return random.betavariate(a, b)


def point_mort(gain_moyen, perte_moyenne):
    """WR (%) tel que WR*gain + (1-WR)*perte = 0. perte_moyenne negative ou positive, peu importe."""
    g, p = abs(gain_moyen or 0), abs(perte_moyenne or 0)
    return round(p / (g + p) * 100, 1) if g + p > 0 else 50.0


# ------------------------------------------------------------------ Sharpe deflate
def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _z(p):
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def moments(gains):
    n = len(gains)
    if n < 3:
        return None
    m = sum(gains) / n
    var = sum((x - m) ** 2 for x in gains) / (n - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return {"moy": m, "sd": 0.0, "skew": 0.0, "kurt": 3.0, "sharpe": 0.0}
    skew = sum(((x - m) / sd) ** 3 for x in gains) / n
    kurt = sum(((x - m) / sd) ** 4 for x in gains) / n
    return {"moy": m, "sd": sd, "skew": skew, "kurt": kurt, "sharpe": m / sd}


def sharpe_deflate(sharpe, n, n_essais=1, skew=0.0, kurt=3.0, var_sharpe_essais=None):
    """Probabilite que le Sharpe observe (par trade) soit > 0 une fois corrige du nombre d'essais, de la
    non-normalite et de la taille d'echantillon. > 0.95 = credible."""
    if n < 3:
        return 0.0
    if n_essais <= 1:
        sr0 = 0.0
    else:
        v = var_sharpe_essais if var_sharpe_essais is not None else 1.0 / max(n, 1)
        e = 0.5772156649
        sr0 = math.sqrt(v) * ((1 - e) * _z(1 - 1.0 / n_essais) + e * _z(1 - 1.0 / (n_essais * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sharpe + (kurt - 1) / 4.0 * sharpe * sharpe))
    z = (sharpe - sr0) * math.sqrt(n - 1) / denom
    return round(_phi(z), 4)


def trades_minimum(wr_pct, ratio_gain_perte=1.0, confiance=0.95):
    """Nombre de trades pour que l'esperance par trade soit > 0 a `confiance`, avec WR et ratio donnes."""
    p = wr_pct / 100.0
    esp = p * ratio_gain_perte - (1 - p)
    if esp <= 0:
        return None
    var = p * ratio_gain_perte ** 2 + (1 - p) - esp ** 2
    z = _z(confiance)
    return int(math.ceil(var * z * z / (esp * esp)))


# ------------------------------------------------------------------ Monte Carlo
def monte_carlo(gains, n_sim=2000, graine=42):
    if not gains:
        return None
    rnd = random.Random(graine)
    dds, finals = [], []
    for _ in range(n_sim):
        # bootstrap (tirage avec remise) : le total varie, le drawdown aussi
        g = [rnd.choice(gains) for _ in gains]
        eq = pic = dd = 0.0
        for x in g:
            eq += x
            pic = max(pic, eq)
            dd = min(dd, eq - pic)
        dds.append(dd)
        finals.append(eq)
    dds.sort(); finals.sort()
    q = lambda arr, p: arr[min(len(arr) - 1, int(p * len(arr)))]
    return {"dd_median": round(q(dds, 0.5), 2), "dd_95": round(q(dds, 0.05), 2), "dd_99": round(q(dds, 0.01), 2),
            "pnl_median": round(q(finals, 0.5), 2), "proba_pnl_negatif": round(sum(1 for f in finals if f < 0) / n_sim, 3)}


def valider_strategie(gains, n_essais=1, niveau=0.90):
    """Verdict complet pour une liste de gains (EUR, frais inclus)."""
    n = len(gains)
    g = sum(1 for x in gains if x > 0)
    post = beta_posterior(g, n)
    mo = moments(gains) or {"sharpe": 0.0, "skew": 0.0, "kurt": 3.0}
    gm = sum(x for x in gains if x > 0) / g if g else 0.0
    pm = sum(x for x in gains if x <= 0) / (n - g) if n - g else 0.0
    pmort = point_mort(gm, pm)
    dsr = sharpe_deflate(mo["sharpe"], n, n_essais, mo["skew"], mo["kurt"])
    mc = monte_carlo(gains) if n >= 10 else None
    nmin = trades_minimum(post["moyenne"], abs(gm / pm) if pm else 1.0)
    credible = n >= 30 and post["ic_bas"] > pmort and dsr >= 0.95 and sum(gains) > 0
    return {"n": n, "wr_bayes": post["moyenne"], "ic90": [post["ic_bas"], post["ic_haut"]], "point_mort": pmort,
            "sharpe_trade": round(mo["sharpe"], 3), "dsr": dsr, "trades_minimum": nmin, "monte_carlo": mc,
            "credible": credible,
            "verdict": "credible" if credible else ("perdante" if n >= 15 and post["ic_haut"] < pmort else "pas assez de preuves")}


if __name__ == "__main__":
    print("Beta(5,5) + 65 % de 40 trades :", beta_posterior(26, 40))
    print("Beta(5,5) + 68 % de 25 trades :", beta_posterior(17, 25))
    print("Point mort gain 0.9 / perte -0.6 :", point_mort(0.9, -0.6), "%")
    print("Trades minimum WR 55 %, ratio 1.2 :", trades_minimum(55, 1.2))
    print("Trades minimum WR 40 %, ratio 2.0 :", trades_minimum(40, 2.0))
    rnd = random.Random(1)
    gains = [1.6 if rnd.random() < 0.42 else -0.9 for _ in range(60)]
    print("Validation d'une serie simulee :", valider_strategie(gains, n_essais=10))
