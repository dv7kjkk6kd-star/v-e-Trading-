"""Strategy Lab – stahování dat pro GitHub Pages (bez API klíčů).
Zdroje: Yahoo Finance přes yfinance (NQ=F po minutě, denní ETF a akcie, výsledky firem, přehled, titulky zpráv),
FRED (CPI, sazba Fedu, výnos 30letých dluhopisů, NFP) a kalendář zpráv z veřejného events.json tvého webu Kompas klidu (jen čtení).
Výstup: lab/data/  (manifest.json, hist.json, m1/RRRR-MM-DD.json)
Použití:  python fetch_lab.py            # minuty NQ (každých 15 min)
          python fetch_lab.py --daily    # navíc denní data, výsledky, makro, sentiment (jednou denně po zavření trhu)
"""
import sys, os, json, re, time, math, datetime as dt, urllib.request, io
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "lab" / "data"
M1 = OUT / "m1"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
NY = ZoneInfo("America/New_York")
ETF = {"WORLD": "EFA", "BOND20": "TLT", "BOND7": "IEF", "GOLD": "GLD", "COMM": "DBC", "EURUSD": "EURUSD=X"}
KEEP_M1_DAYS = 35

def log(*a): print(dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"), *a, flush=True)
def rj(p, d):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d
def wj(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8"); tmp.replace(p)
def r6(x):
    try: x = float(x)
    except (TypeError, ValueError): return None
    return None if math.isnan(x) or math.isinf(x) else round(x, 6)

def session_date(ts):
    """NQ seance začíná v 18:00 NY a patří k dalšímu obchodnímu dni."""
    t = ts.astimezone(NY); d = t.date()
    if t.hour >= 18:
        d = d + dt.timedelta(days=3 if t.weekday() == 4 else 2 if t.weekday() == 5 else 1)
    return d.isoformat(), t.hour * 60 + t.minute

# ---------- minuty NQ ----------
def frame_rows(df):
    """DataFrame z yfinance (index = čas) → [[ms,o,h,l,c,v]]."""
    if df is None or len(df) == 0: return []
    if hasattr(df.columns, "levels"): df = df.droplevel(1, axis=1) if df.columns.nlevels > 1 else df
    out = []
    for ts, r in df.iterrows():
        try: o, h, l, c, v = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), float(r.get("Volume", 0) or 0)
        except Exception: continue
        if any(math.isnan(x) for x in (o, h, l, c)): continue
        if ts.tzinfo is None: ts = ts.tz_localize("UTC")
        out.append([int(ts.timestamp() * 1000), round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(v if not math.isnan(v) else 0)])
    return out

def update_minutes(yf):
    df = yf.download("NQ=F", period="7d", interval="1m", progress=False, auto_adjust=False, prepost=True, threads=False)
    rows = frame_rows(df)
    log("NQ=F 1m:", len(rows), "svíček")
    by = {}
    for r in rows:
        d, clock = session_date(dt.datetime.fromtimestamp(r[0] / 1000, dt.timezone.utc))
        if 1020 <= clock < 1080: continue
        by.setdefault(d, []).append(r)
    for d, new in by.items():
        p = M1 / f"{d}.json"; old = rj(p, [])
        m = {x[0]: x for x in old}
        for x in new: m[x[0]] = x
        wj(p, sorted(m.values()))
    days = sorted(f.stem for f in M1.glob("*.json"))
    for f in days[:-KEEP_M1_DAYS]: (M1 / f"{f}.json").unlink(missing_ok=True)
    return sorted(f.stem for f in M1.glob("*.json"))

# ---------- denní data ----------
def daily_rows(df):
    out = []
    for ts, r in df.iterrows():
        try: o, h, l, c, v = (float(r[k]) for k in ("Open", "High", "Low", "Close", "Volume"))
        except Exception: continue
        if any(math.isnan(x) for x in (o, h, l, c)): continue
        out.append([ts.strftime("%Y-%m-%d"), r6(o), r6(h), r6(l), r6(c), int(0 if math.isnan(v) else v)])
    return out

def fred(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as r:
        text = r.read().decode()
    rows = []
    for line in text.strip().splitlines()[1:]:
        d, v = line.split(",")[:2]
        try: rows.append([d, float(v)])
        except ValueError: pass
    return rows

POS = set("beat beats record surge surges soar soars jump jumps rally rallies gain gains rise rises upgrade upgraded strong growth profit profits raises raised boost boosts outperform bullish win wins approval approved breakthrough expands expansion higher top tops buyback dividend partnership".split())
NEG = set("miss misses plunge plunges fall falls drop drops slump slumps cut cuts downgrade downgraded weak loss losses lawsuit probe investigation recall bearish warning warns layoffs decline declines lower risk risks fine fined slowdown halt halts fraud bankruptcy concern concerns underperform sinks sink tumble tumbles".split())
def headline_score(t):
    w = re.findall(r"[a-z]+", t.lower()); p = sum(x in POS for x in w); n = sum(x in NEG for x in w)
    return 0.0 if p + n == 0 else (p - n) / (p + n)

def fnum(s):
    if s is None: return None
    s = str(s).replace(",", "").replace("%", "").strip().upper()
    mult = 1
    if s.endswith("K"): s, mult = s[:-1], 1e3
    elif s.endswith("M"): s, mult = s[:-1], 1e6
    elif s.endswith("B"): s, mult = s[:-1], 1e9
    try: return float(s) * mult
    except ValueError: return None

def events_from_briefing():
    """Kalendář z events.json tvého webu (Forex Factory, jen čtení). Jen CPI, NFP a FOMC, které umí news skalp."""
    ev = []
    try:
        with urllib.request.urlopen(urllib.request.Request(CFG.get("events_url", "https://dv7kjkk6kd-star.github.io/1/events.json"), headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            ev = json.loads(r.read().decode("utf-8"))
        if not isinstance(ev, list): ev = []
    except Exception as e:
        print("events.json nedostupný, použiju jen pravidla:", e)
    out = []
    for e in ev:
        t = (e.get("t") or ""); ts = e.get("ts")
        typ = "CPI" if re.search(r"\bCPI m/m\b|\bCPI y/y\b", t) else "NFP" if "Non-Farm Employment Change" in t else "FOMC" if ("Federal Funds Rate" in t or "FOMC Statement" in t) else None
        if not typ or not ts: continue
        tny = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).astimezone(NY)
        f, a = fnum(e.get("f")), fnum(e.get("a"))
        z = None
        if f is not None and a is not None:
            scale = {"CPI": 0.1, "NFP": 60000 if abs(f) > 1000 else 60, "FOMC": 0.1}[typ]; z = max(-4, min(4, (a - f) / scale))
        react = 0.6 if typ == "NFP" else -1
        out.append({"date": tny.date().isoformat(), "clock": tny.hour * 60 + tny.minute, "type": typ, "name": t, "exp": e.get("f"), "act": e.get("a"), "z": z, "react": react})
    seen, uniq = set(), []
    for e in sorted(out, key=lambda x: (x["date"], x["type"])):
        k = (e["date"], e["type"])
        if k in seen: continue
        seen.add(k); uniq.append(e)
    return uniq

def rule_events(have):
    """NFP = první pátek v měsíci 8:30, FOMC podle config.json (pokud chybí v kalendáři briefingu)."""
    out = []; y0 = 2015; y1 = dt.date.today().year + 1
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            d = dt.date(y, m, 1)
            while d.weekday() != 4: d += dt.timedelta(days=1)
            if (d.isoformat(), "NFP") not in have: out.append({"date": d.isoformat(), "clock": 510, "type": "NFP", "name": "NFP – nová pracovní místa", "react": 0.6})
    for d in CFG.get("fomc", []):
        if (d, "FOMC") not in have: out.append({"date": d, "clock": 840, "type": "FOMC", "name": "FOMC – rozhodnutí o sazbách", "react": -1})
    return out

def update_daily(yf, hist):
    syms = [s["sym"] for s in CFG["stocks"]]
    tickers = ["NQ=F"] + list(ETF.values()) + syms
    df = yf.download(tickers, period="11y", interval="1d", progress=False, auto_adjust=True, group_by="ticker", threads=True)
    daily = {}
    for t in tickers:
        try: rows = daily_rows(df[t])
        except Exception as e: log("chybí", t, e); continue
        key = "NQ" if t == "NQ=F" else next((k for k, v in ETF.items() if v == t), t)
        if len(rows) > 50: daily[key] = rows
    log("denní řady:", len(daily))
    hist["nqDaily"] = daily.pop("NQ", hist.get("nqDaily", []))
    hist["daily"] = {**hist.get("daily", {}), **daily}
    # výsledky, přehled a titulky
    earn, over, sent = hist.get("earnings", {}), hist.get("overview", {}), hist.get("sentiment", {})
    today = dt.datetime.now(NY).date().isoformat()
    for s in syms:
        tk = yf.Ticker(s)
        try:
            ed = tk.get_earnings_dates(limit=48)
            if ed is not None and len(ed):
                L = []
                for ts, r in ed.iterrows():
                    eps, est, sp = r.get("Reported EPS"), r.get("EPS Estimate"), r.get("Surprise(%)")
                    if eps is None or (isinstance(eps, float) and math.isnan(eps)): continue
                    d = ts.tz_convert(NY) if ts.tzinfo else ts
                    rep = (d + dt.timedelta(days=1)).date().isoformat() if d.hour >= 16 else d.date().isoformat()   # po zavření → známé další den
                    L.append({"rep": rep, "eps": r6(eps), "est": r6(est), "sp": r6(sp)})
                if L: earn[s] = sorted(L, key=lambda x: x["rep"])
        except Exception as e: log("výsledky", s, e)
        try:
            i = tk.info or {}
            de = i.get("debtToEquity")
            over[s] = {"name": i.get("shortName") or s, "roe": i.get("returnOnEquity"), "margin": i.get("profitMargins"), "growth": i.get("earningsGrowth"), "pe": i.get("trailingPE"), "de": (de / 100 if isinstance(de, (int, float)) else None)}
        except Exception as e: log("přehled", s, e)
        try:
            news = tk.news or []
            sc = []
            for n in news[:20]:
                t = n.get("title") or (n.get("content") or {}).get("title") or ""
                if t: sc.append(headline_score(t))
            if sc: sent.setdefault(s, {})[today] = round(sum(sc) / len(sc), 4)
        except Exception as e: log("zprávy", s, e)
        time.sleep(0.4)
    hist["earnings"], hist["overview"], hist["sentiment"] = earn, over, sent
    macro = hist.get("macro", {})
    for key, sid in (("cpi", "CPIAUCSL"), ("ff", "DFF"), ("y30", "DGS30"), ("nfp", "PAYEMS")):
        try: macro[key] = [r for r in fred(sid) if r[0] >= "2014-01-01"]
        except Exception as e: log("FRED", sid, e)
    hist["macro"] = macro
    ev = events_from_briefing(); have = {(e["date"], e["type"]) for e in ev}
    old = [e for e in hist.get("events", []) if (e["date"], e["type"]) not in have and e.get("src") == "ff"]
    hist["events"] = sorted([dict(e, src="ff") for e in ev] + old + rule_events(have | {(e["date"], e["type"]) for e in old}), key=lambda e: (e["date"], e["clock"]))
    hist["stocks"] = [{"sym": s["sym"], "name": (over.get(s["sym"]) or {}).get("name") or s["name"], "sec": s["sec"]} for s in CFG["stocks"] if s["sym"] in hist["daily"]]
    hist["pairs"] = [p for p in CFG.get("pairs", []) if p[0] in hist["daily"] and p[1] in hist["daily"]]
    hist["lastDaily"] = max((r[-1][0] for r in hist["daily"].values() if r), default=None)
    hist["dailyAt"] = int(time.time() * 1000)
    return hist

def main():
    import yfinance as yf
    OUT.mkdir(parents=True, exist_ok=True); M1.mkdir(parents=True, exist_ok=True)
    days = update_minutes(yf)
    hist = rj(OUT / "hist.json", {})
    now = dt.datetime.now(NY); at = hist.get("dailyAt")
    done_today = at and dt.datetime.fromtimestamp(at / 1000, NY).date() == now.date() and dt.datetime.fromtimestamp(at / 1000, NY).hour * 60 + dt.datetime.fromtimestamp(at / 1000, NY).minute >= 980
    daily = "--daily" in sys.argv or not hist.get("daily") or (now.weekday() < 5 and now.hour * 60 + now.minute >= 980 and not done_today)
    if daily:
        hist = update_daily(yf, hist); wj(OUT / "hist.json", hist)
    last = None
    if days:
        rows = rj(M1 / f"{days[-1]}.json", [])
        last = rows[-1][0] if rows else None
    man = {"v": 1, "updated": int(time.time() * 1000), "m1Days": days, "lastMinute": last, "histAt": hist.get("dailyAt"), "source": "Yahoo Finance (NQ=F), FRED, Forex Factory"}
    wj(OUT / "manifest.json", man)
    log("hotovo:", len(days), "dní minut, poslední", dt.datetime.fromtimestamp(last / 1000, NY).strftime("%d.%m. %H:%M NY") if last else "–")

if __name__ == "__main__":
    main()
