"""Make SAMPLE data for design previews. These are not real statistics.

build_site.py uses this only when data/live/ has nothing, and every page then shows a sample banner.
"""
import json
import random
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample"
LETTERS = "ABCDEFGHIJKLMNOP"


def emp(i):
    return f"Sample Employer {LETTERS[i % 16]}{'' if i < 16 else i // 16 + 1}"


def main():
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    rnd = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    states = ["CA", "WA", "TX", "NY", "NJ", "IL", "MA", "GA"]
    jstates = ["TX", "GA", "NC", "AR", "IA", "NE", "OH", "IN", "AL", "CA"]
    countries = ["India", "Mexico", "Philippines", "China", "Guatemala", "South Korea", "Vietnam", "Brazil"]

    lca, perm, sc = {}, {}, {}
    for m in cfg["majors"]:
        for soc in m["soc"]:
            if soc in lca:
                continue
            base = rnd.randint(70, 150) * 1000
            n = rnd.randint(800, 60000)
            lca[soc] = {
                "filings": n, "wage_p25": int(base * 0.82), "wage_median": base, "wage_p75": int(base * 1.25),
                "top_employers": [{"name": emp(i), "filings": int(n * (0.08 - i * 0.006)),
                                   "wage_median": int(base * rnd.uniform(0.9, 1.3))} for i in range(8)],
                "top_states": [{"state": s, "filings": int(n * w)} for s, w in
                               zip(rnd.sample(states, 5), [0.24, 0.15, 0.11, 0.08, 0.06])],
            }
            dec = int(n * rnd.uniform(0.08, 0.3))
            cert = int(dec * rnd.uniform(0.88, 0.97))
            perm[soc] = {"decisions": dec, "certified": cert, "cert_rate": round(cert / dec * 100, 1),
                         "days_median": rnd.randint(420, 560),
                         "top_employers": [{"name": emp(i), "certified": int(cert * (0.1 - i * 0.008))} for i in range(8)]}
        b = rnd.randint(55, 105) * 1000
        rows = [{"school": f"Sample University {i + 1}", "unitid": str(100000 + i), "earn_1yr": int(b * (1.35 - i * 0.04)),
                 "earn_later": int(b * (1.35 - i * 0.04) * 1.3), "count": rnd.randint(20, 400)} for i in range(12)]
        sc[m["cip4"]] = {"3": {"programs": rnd.randint(150, 900), "median_earn_1yr": b, "top": rows},
                         "5": {"programs": rnd.randint(60, 300), "median_earn_1yr": int(b * 1.2),
                               "top": [dict(r, earn_1yr=int(r["earn_1yr"] * 1.2)) for r in rows]}}

    for j in cfg["jobs"]:
        soc = j["soc"]
        base = int(rnd.uniform(16, 32) * 2080)
        cert = rnd.randint(150, 6000)
        dec = int(cert / rnd.uniform(0.86, 0.97))
        perm[soc] = {
            "decisions": dec, "certified": cert, "cert_rate": round(cert / dec * 100, 1),
            "wage_p25": int(base * 0.9), "wage_median": base, "wage_p75": int(base * 1.12),
            "days_median": rnd.randint(430, 600),
            "top_countries": [{"country": c, "certified": int(cert * w)} for c, w in
                              zip(rnd.sample(countries, 6), [0.3, 0.18, 0.12, 0.08, 0.05, 0.03])],
            "top_employers": [{"name": emp(i), "certified": int(cert * (0.12 - i * 0.007)),
                               "wage_median": int(base * rnd.uniform(0.92, 1.1))} for i in range(12)],
            "top_states": [{"state": s, "certified": int(cert * w)} for s, w in
                           zip(rnd.sample(jstates, 6), [0.22, 0.15, 0.12, 0.09, 0.07, 0.05])],
        }
        lca.setdefault(soc, {"filings": 0})

    socs_all = [j["soc"] for j in cfg["jobs"]]
    employers = sorted(({"n": f"SAMPLE EMPLOYER {i + 1:02d}", "c": int(d * rnd.uniform(0.7, 1)), "d": d,
                         "s": rnd.sample(socs_all, 2), "st": rnd.choice(jstates)}
                        for i, d in enumerate(rnd.randint(3, 400) for _ in range(60))), key=lambda x: -x["d"])

    vb_hist = []
    for k in range(12):
        y, m = 2025 + (10 + k) // 12, (10 + k) % 12 + 1
        vb_hist.append({"month": f"{y}-{m:02d}",
                        "eb3_final": f"2023-{min(12, 1 + k // 2):02d}-01", "ew_final": f"2021-{min(12, 1 + k // 3):02d}-01",
                        "eb3_filing": f"2024-{min(12, 1 + k // 2):02d}-01", "ew_filing": f"2022-{min(12, 1 + k // 3):02d}-01"})

    # Canada ------------------------------------------------------------
    provs = ["Ontario", "Alberta", "British Columbia", "Quebec", "Manitoba", "Saskatchewan", "Nova Scotia"]
    streams = ["Low-wage", "High-wage", "Permanent Residence", "Agricultural stream", "Seasonal Agricultural Worker Program"]
    by_noc = {}
    for j in cfg["jobs"]:
        pos = rnd.randint(200, 9000)
        by_noc[j["noc"]] = {
            "positions": pos, "employers": int(pos / rnd.uniform(2, 6)), "pr_positions": int(pos * rnd.uniform(0.05, 0.25)),
            "top_employers": [{"name": emp(i), "positions": int(pos * (0.06 - i * 0.003)),
                               "province": rnd.choice(provs)} for i in range(12)],
            "top_provinces": [{"province": p, "positions": int(pos * w)} for p, w in
                              zip(rnd.sample(provs, 6), [0.3, 0.2, 0.15, 0.1, 0.07, 0.05])],
            "streams": [{"stream": s, "positions": int(pos * w)} for s, w in
                        zip(rnd.sample(streams, 4), [0.5, 0.25, 0.15, 0.1])],
        }
    ee = [{"no": 380 - i, "date": f"2026-{10 - i // 4:02d}-{28 - (i % 4) * 7:02d}",
           "name": rnd.choice(["Canadian Experience Class", "Provincial Nominee Program", "Healthcare and social services occupations",
                               "Trade occupations", "French language proficiency"]),
           "size": rnd.choice([500, 1000, 2500, 3000, 4500]), "crs": rnd.randint(380, 820)} for i in range(16)]
    ca = {"period": "Sample", "total_positions": 98000, "by_noc": by_noc, "ee": ee}
    nocs_all = [j["noc"] for j in cfg["jobs"]]
    ca_emp = sorted(({"n": f"SAMPLE EMPLOYER {i + 1:02d}", "p": rnd.randint(2, 300), "o": rnd.sample(nocs_all, 2),
                      "pv": rnd.choice(provs)} for i in range(60)), key=lambda x: -x["p"])

    # United Kingdom ------------------------------------------------------
    routes = [("Skilled Worker", 118000), ("Global Business Mobility: Senior or Specialist Worker", 4100),
              ("Scale-up", 1200), ("Seasonal Worker", 40), ("Creative Worker", 1900), ("Charity Worker", 900),
              ("Religious Worker", 1100), ("International Sport", 700)]
    towns = ["London", "Birmingham", "Manchester", "Leeds", "Glasgow", "Bristol", "Leicester", "Liverpool", "Sheffield", "Edinburgh"]
    uk = {"date": "Sample", "organisations": 125000, "skilled_worker": 118000,
          "routes": [{"route": r, "count": c} for r, c in routes],
          "top_towns": [{"town": t, "count": int(30000 / (i + 1) ** 0.9)} for i, t in enumerate(towns)]}
    uk_idx = [{"n": f"SAMPLE SPONSOR {i + 1:02d} LTD", "t": rnd.choice(towns),
               "r": ["Skilled Worker"] + (["Global Business Mobility: Senior or Specialist Worker"] if i % 5 == 0 else [])}
              for i in range(80)]

    au_states = ["Victoria", "New South Wales", "Queensland", "Western Australia", "South Australia", "Tasmania"]
    au_jobs = {}
    for j in cfg["jobs"]:
        g = rnd.randint(80, 4000)
        au_jobs[j["slug"]] = {
            "grants": g, "grants_prev": int(g * rnd.uniform(0.7, 1.3)),
            "top_countries": [{"name": c, "grants": int(g * w)} for c, w in
                              zip(rnd.sample(countries, 6), [0.3, 0.18, 0.12, 0.08, 0.05, 0.03])],
            "top_states": [{"name": s, "grants": int(g * w)} for s, w in
                           zip(rnd.sample(au_states, 6), [0.3, 0.25, 0.2, 0.1, 0.06, 0.03])],
            "subtypes": [{"name": "Core Skills", "grants": int(g * 0.7)}, {"name": "Labour Agreement", "grants": int(g * 0.2)}],
            "industries": [{"name": "Manufacturing", "grants": int(g * 0.4)}, {"name": "Accommodation and Food Services", "grants": int(g * 0.2)}],
        }
    au = {"as_at": "sample", "window": "Oct 2025 – Sep 2026", "total_grants": 60000, "by_job": au_jobs}

    korea_e9 = {"year": "Sample", "by_nationality": [{"country": c, "workers": n} for c, n in zip(
        ["Nepal", "Cambodia", "Vietnam", "Indonesia", "Myanmar", "Sri Lanka", "Bangladesh", "Philippines", "Thailand", "Uzbekistan"],
        [52000, 45000, 41000, 30000, 28000, 26000, 21000, 19000, 17000, 15000])],
        "by_region": [{"region": r, "workers": n} for r, n in zip(
            ["Gyeonggi", "Gyeongnam", "Chungnam", "Gyeongbuk", "Chungbuk", "Jeonnam", "Incheon"],
            [120000, 42000, 36000, 33000, 26000, 22000, 18000])]}

    meta = {"sample": True, "generated": "sample", "lca": {"period": "sample"}, "perm": {"period": "sample"}, "scorecard": {}}
    files = {"meta": meta, "lca": lca, "perm": perm, "scorecard": sc, "employers": employers,
             "visa_bulletin": {"current": vb_hist[-1], "history": vb_hist},
             "ca": ca, "ca_employers": ca_emp, "uk": uk, "uk_sponsors": uk_idx, "korea_e9": korea_e9, "au": au}
    for name, obj in files.items():
        (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    print("Sample data written to", OUT)


if __name__ == "__main__":
    main()
