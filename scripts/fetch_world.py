"""캐나다·영국 공공데이터를 받아 요약 JSON(data/live/)을 만듭니다.

    python scripts/fetch_world.py          # 둘 다
    python scripts/fetch_world.py ca       # 캐나다만
    python scripts/fetch_world.py uk       # 영국만

원본
- 캐나다 고용사회개발부(ESDC): 노동시장영향평가(LMIA) 승인 고용주 목록 (분기)
- 캐나다 이민부(IRCC): Express Entry 영주권 초청 추첨 결과
- 영국 내무부(Home Office): 취업비자 스폰서 등록 회사 명단 (매일 갱신)
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data" / "live"
HEADERS = {"User-Agent": "us-career-map/1.0 (public data research)"}

PROVINCE_KO: dict[str, str] = {}  # province names are kept in English


def log(msg):
    print(msg, flush=True)


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=300, **kw)
    r.raise_for_status()
    return r


def num(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except ValueError:
        return 0


# ---------------------------------------------------------------- 캐나다 LMIA
def latest_lmia_url(package_api: str) -> tuple[str, str]:
    res = get(package_api).json()["result"]["resources"]
    best = None
    for r in res:
        name = (r.get("name") or "") + " " + (r.get("url") or "")
        m = re.search(r"(20\d\d)\s*-?\s*Q([1-4])", name, re.I)
        lang = r.get("language") or []
        is_en = "en" in lang or re.search(r"[_\-\s]EN\b|english", name, re.I)
        if not m or not is_en or not r.get("url", "").lower().endswith((".xlsx", ".xls", ".csv")):
            continue
        key = (int(m.group(1)), int(m.group(2)))
        if best is None or key > best[0]:
            best = (key, r["url"])
    if not best:
        raise RuntimeError("LMIA 파일을 찾지 못했습니다")
    return best[1], f"Q{best[0][1]} {best[0][0]}"


def read_lmia(content: bytes, url: str) -> pd.DataFrame:
    if url.lower().endswith(".csv"):
        raw = pd.read_csv(io.BytesIO(content), header=None, dtype=str, encoding="latin-1")
    else:
        raw = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
    # 제목 줄이 몇 줄 있으므로 'Employer'가 들어간 줄을 머리글로 씁니다
    def is_header(row):
        cells = " | ".join(str(v).lower() for v in row.values if pd.notna(v))
        return sum(w in cells for w in ("employer", "occupation", "province", "position")) >= 3

    hdr = next(i for i in range(min(30, len(raw))) if is_header(raw.iloc[i]))
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hdr]]
    return df


def col(df, *words):
    for c in df.columns:
        if all(w in c.lower() for w in words):
            return c
    return None


def fetch_ca(cfg: dict) -> dict:
    src = cfg["sources"]
    url, period = latest_lmia_url(src["ca_lmia_package"])
    log(f"  LMIA {period}: {url}")
    df = read_lmia(get(url).content, url)
    c_prov, c_stream, c_emp = col(df, "province"), col(df, "stream"), col(df, "employer")
    c_occ, c_pos, c_lmia = col(df, "occupation"), col(df, "position"), col(df, "approved", "lmia")
    log(f"  사용한 열: 주={c_prov}, 프로그램={c_stream}, 회사={c_emp}, 직업={c_occ}, 인원={c_pos}")
    df = df[df[c_emp].notna()]
    df["_noc"] = df[c_occ].astype(str).str.extract(r"^(\d{5})")[0]
    df["_pos"] = df[c_pos].map(num) if c_pos else 1
    df["_emp"] = df[c_emp].astype(str).str.strip().str.upper()
    df["_prov"] = df[c_prov].astype(str).str.strip() if c_prov else ""
    df["_stream"] = df[c_stream].astype(str).str.strip() if c_stream else ""

    nocs = {j["noc"] for j in cfg.get("jobs", []) if j.get("noc")}
    by_noc = {}
    for noc, g in df[df["_noc"].isin(nocs)].groupby("_noc"):
        emp = g.groupby("_emp")["_pos"].sum().sort_values(ascending=False)
        prov = g.groupby("_prov")["_pos"].sum().sort_values(ascending=False)
        stream = g.groupby("_stream")["_pos"].sum().sort_values(ascending=False)
        pr = int(g[g["_stream"].str.contains("permanent", case=False)]["_pos"].sum())
        by_noc[noc] = {
            "positions": int(g["_pos"].sum()),
            "employers": int(g["_emp"].nunique()),
            "pr_positions": pr,
            "top_employers": [{"name": e, "positions": int(n),
                               "province": g[g["_emp"] == e]["_prov"].iloc[0]} for e, n in emp.head(15).items()],
            "top_provinces": [{"province": PROVINCE_KO.get(p, p), "positions": int(n)} for p, n in prov.head(6).items()],
            "streams": [{"stream": s, "positions": int(n)} for s, n in stream.items()],
        }

    index = []
    for e, g in df.groupby("_emp"):
        index.append({"n": e, "p": int(g["_pos"].sum()),
                      "o": [n for n, _ in Counter(g["_noc"].dropna()).most_common(3)],
                      "pv": PROVINCE_KO.get(g["_prov"].iloc[0], g["_prov"].iloc[0])})
    index.sort(key=lambda x: -x["p"])

    ee = fetch_ee(src.get("ca_ee_rounds"))
    return {"period": period, "url": url, "total_positions": int(df["_pos"].sum()),
            "by_noc": by_noc, "ee": ee}, index[:8000]


def fetch_ee(url: str | None) -> list:
    """Express Entry 추첨 결과. 실패해도 나머지 갱신은 계속합니다."""
    if not url:
        return []
    try:
        data = get(url).json()
        rounds = data.get("rounds") or data.get("data") or []
        out = []
        for r in rounds[:40]:
            out.append({
                "no": r.get("drawNumber") or r.get("drawNumberURL"),
                "date": r.get("drawDate") or r.get("drawDateFull"),
                "name": r.get("drawName") or r.get("drawType") or "",
                "size": num(r.get("drawSize", 0)),
                "crs": num(r.get("drawCRS", 0)),
            })
        log(f"  Express Entry 추첨 {len(out)}건")
        return out
    except Exception as e:  # noqa: BLE001
        log(f"  Express Entry 가져오기 실패: {e}")
        return []


# ---------------------------------------------------------------- 영국 스폰서
def fetch_uk(cfg: dict):
    api = cfg["sources"]["uk_sponsor_api"]
    text = get(api).text
    links = re.findall(r'https://assets\.publishing\.service\.gov\.uk/[^"\\]+?\.csv', text)
    if not links:
        raise RuntimeError("영국 스폰서 CSV 링크를 찾지 못했습니다")
    url = links[0]
    m = re.search(r"(20\d\d-\d\d-\d\d)", url)
    log(f"  스폰서 명단: {url}")
    df = pd.read_csv(io.BytesIO(get(url).content), dtype=str, encoding="utf-8", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    c_name, c_town = col(df, "organisation"), col(df, "town")
    c_route, c_type = col(df, "route"), col(df, "type")
    df["_n"] = df[c_name].astype(str).str.strip().str.upper()
    df["_t"] = df[c_town].astype(str).str.strip().str.title() if c_town else ""
    df["_r"] = df[c_route].astype(str).str.strip() if c_route else ""

    routes = Counter(df["_r"])
    towns = Counter(df.drop_duplicates("_n")["_t"])
    index = []
    for n, g in df.groupby("_n"):
        index.append({"n": n, "t": g["_t"].iloc[0], "r": sorted(set(g["_r"]))})
    index.sort(key=lambda x: x["n"])
    summary = {
        "date": m.group(1) if m else dt.date.today().isoformat(),
        "url": url,
        "organisations": len(index),
        "routes": [{"route": r, "count": c} for r, c in routes.most_common(12)],
        "top_towns": [{"town": t, "count": c} for t, c in towns.most_common(10)],
        "skilled_worker": routes.get("Skilled Worker", 0),
    }
    return summary, index


# ---------------------------------------------------------------- Australia
QUARTER_MONTHS = {"Q1": ("Jul", "Sep", 0), "Q2": ("Oct", "Dec", 0), "Q3": ("Jan", "Mar", 1), "Q4": ("Apr", "Jun", 1)}


def au_grants_url(package_api: str) -> tuple[str, str]:
    res = get(package_api).json()["result"]["resources"]
    for r in res:
        name = (r.get("name") or "").lower()
        if "granted" in name and r.get("url", "").lower().endswith(".xlsx"):
            m = re.search(r"(20\d\d-\d\d-\d\d)", r["name"] + r["url"])
            return r["url"], m.group(1) if m else ""
    raise RuntimeError("Australian visa grants file not found")


def read_pivot_cache(path: Path):
    """Yield dict rows from the pivot cache inside a Home Affairs pivot-table workbook."""
    import xml.etree.ElementTree as ET
    import zipfile
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as z:
        defn = next(n for n in z.namelist() if n.startswith("xl/pivotCache/pivotCacheDefinition"))
        recs = defn.replace("Definition", "Records")
        root = ET.fromstring(z.read(defn))
        fields = []
        for f in root.iter(ns + "cacheField"):
            si = f.find(ns + "sharedItems")
            items = [c.get("v") for c in si] if si is not None else []
            fields.append((f.get("name"), items))
        with z.open(recs) as fh:
            for _, el in ET.iterparse(fh):
                if el.tag != ns + "r":
                    continue
                row = {}
                for (name, items), c in zip(fields, el):
                    v = c.get("v")
                    if c.tag == ns + "x":
                        row[name] = items[int(v)] if items else v
                    elif c.tag == ns + "n":
                        row[name] = float(v)
                    else:
                        row[name] = v
                yield row
                el.clear()


def fetch_au(cfg: dict) -> dict:
    url, as_at = au_grants_url(cfg["sources"]["au_package"])
    log(f"  Australia grants file ({as_at}): {url}")
    path = RAW / Path(url).name
    RAW.mkdir(exist_ok=True)
    if not path.exists():
        path.write_bytes(get(url).content)

    jobs = {j["slug"]: j.get("anzsco") or [] for j in cfg.get("jobs", [])}

    def job_of(unit):
        unit = unit or ""
        for slug, codes in jobs.items():
            if any(unit == c or unit.startswith(c + " ") for c in codes):
                return slug
        return None

    by_period = Counter()
    agg = defaultdict(lambda: defaultdict(Counter))
    for r in read_pivot_cache(path):
        if r.get("Applicant Type") != "Primary":
            continue
        n = r.get("Total", 1) or 0
        period = (r.get("Financial Year of Visa Grant"), (r.get("Financial Year Quarter") or "")[:2])
        by_period[period] += n
        slug = job_of(r.get("Nominated Occupation (Unit Group)"))
        if slug:
            a = agg[slug]
            a["period"][period] += n
            a["country"][(period, r.get("Citizenship Country"))] += n
            a["state"][(period, r.get("Nominated Position Location (State)"))] += n
            a["subtype"][(period, r.get("Visa Sub-type"))] += n
            a["industry"][(period, r.get("Sponsor Industry"))] += n

    periods = sorted(p for p in by_period if p[0] and p[1])
    last4, prev4 = set(periods[-4:]), set(periods[-8:-4])

    def label(p):
        fy, q = p
        start, end, add = QUARTER_MONTHS[q]
        year = int(fy[:4]) + add
        return start, end, year

    s0, _, y0 = label(periods[-4])
    _, e1, y1 = label(periods[-1])
    window = f"{s0} {y0} – {e1} {y1}"

    def top(counter, k):
        c = Counter()
        for (p, name), n in counter.items():
            if p in last4 and name and name != "Not Specified":
                c[name] += n
        return [{"name": name, "grants": int(n)} for name, n in c.most_common(k)]

    out = {}
    for slug, a in agg.items():
        out[slug] = {
            "grants": int(sum(n for p, n in a["period"].items() if p in last4)),
            "grants_prev": int(sum(n for p, n in a["period"].items() if p in prev4)),
            "top_countries": top(a["country"], 6),
            "top_states": top(a["state"], 6),
            "subtypes": top(a["subtype"], 5),
            "industries": top(a["industry"], 3),
            "korea": int(sum(n for (p, name), n in a["country"].items()
                             if p in last4 and name and name.startswith("Korea, South"))),
        }
    total = int(sum(n for p, n in by_period.items() if p in last4))
    log(f"  Australia: {total} primary grants in {window}, {len(out)} jobs matched")
    return {"as_at": as_at, "window": window, "total_grants": total, "by_job": out, "url": url}


def main(argv: list[str]) -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    want = set(argv) or {"ca", "uk", "au"}
    ok = True
    if "ca" in want:
        log("캐나다")
        try:
            ca, idx = fetch_ca(cfg)
            (OUT / "ca.json").write_text(json.dumps(ca, ensure_ascii=False), encoding="utf-8")
            (OUT / "ca_employers.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")),
                                                   encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log(f"  캐나다 실패: {e}")
            ok = False
    if "uk" in want:
        log("영국")
        try:
            uk, idx = fetch_uk(cfg)
            (OUT / "uk.json").write_text(json.dumps(uk, ensure_ascii=False), encoding="utf-8")
            (OUT / "uk_sponsors.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log(f"  영국 실패: {e}")
            ok = False
    if "au" in want:
        log("Australia")
        try:
            au = fetch_au(cfg)
            (OUT / "au.json").write_text(json.dumps(au, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log(f"  Australia failed: {e}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
