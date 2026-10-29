"""미국 공공데이터를 내려받아 전공별 요약 JSON(data/live/)을 만듭니다.

GitHub Actions에서 매월 자동 실행되며, 직접 실행해도 됩니다.
    python scripts/fetch_data.py

원본
- 미 노동부(DOL) OFLC: H-1B(LCA) 공개 데이터, 영주권(PERM) 공개 데이터
- 미 교육부 College Scorecard: 학교·전공별 졸업 후 소득
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "data" / "live"
HEADERS = {"User-Agent": "us-career-map/1.0 (public data research)"}

WAGE_MULT = {"year": 1, "hour": 2080, "month": 12, "week": 52, "bi-weekly": 26}


# ---------------------------------------------------------------- 공통 유틸
def log(msg: str) -> None:
    print(msg, flush=True)


def pick(df: pd.DataFrame, *candidates: str) -> str | None:
    """DOL은 해마다 열 이름을 바꿉니다. 후보 중 존재하는 첫 열을 고릅니다."""
    cols = {c.upper().strip(): c for c in df.columns}
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    return None


def norm_soc(v) -> str:
    m = re.match(r"\s*(\d{2})-?(\d{4})", str(v))
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        log(f"  캐시 사용: {dest.name}")
        return dest
    log(f"  다운로드: {url}")
    if "dol.gov" in url:
        code, _ = curl(url, dest)
        log(f"  curl download -> {code}")
        if code == 200 and dest.exists() and dest.stat().st_size > 100_000:
            return dest
        dest.unlink(missing_ok=True)
    hdrs = DOL_HEADERS if "dol.gov" in url else HEADERS
    with requests.get(url, headers=hdrs, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    return dest


DOL_PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"


def curl(url: str, out: Path | None = None) -> tuple[int, bytes]:
    """curl with browser-like headers; some sites accept it when python-requests is refused."""
    import subprocess
    cmd = ["curl", "-sSL", "--compressed", "--max-time", "900", "-A", DOL_HEADERS["User-Agent"],
           "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "-H", "Accept-Language: en-US,en;q=0.9", "-w", "%{http_code}"]
    if out:
        cmd += ["-o", str(out)]
    r = subprocess.run(cmd + [url], capture_output=True, timeout=1000)
    body = r.stdout
    code = int(body[-3:] or 0) if body[-3:].isdigit() else 0
    return code, (b"" if out else body[:-3])


def dol_get_text(url: str) -> str:
    r = requests.get(url, headers=DOL_HEADERS, timeout=60)
    log(f"  {url} -> requests {r.status_code}")
    if r.status_code == 200 and "Disclosure" in r.text:
        return r.text
    code, body = curl(url)
    log(f"  {url} -> curl {code}")
    return body.decode("utf-8", "ignore") if code == 200 else ""
# dol.gov rejects some non-browser clients, so identify as a normal browser for those requests
DOL_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/124.0 Safari/537.36", "Accept": "*/*"}


def find_latest(base: str, pattern: str) -> tuple[str, str]:
    """Find the newest quarterly disclosure file.

    Reads the links on the DOL performance page first (files move between folders),
    then falls back to guessing URLs in the known folders.
    """
    prefix = pattern.split("{fy}")[0]          # e.g. "LCA_Disclosure_Data_FY"
    rx = re.compile(re.escape(prefix) + r"(\d{4})_Q([1-4])\.xlsx", re.I)
    try:
        html = dol_get_text(DOL_PAGE)
        found = {}
        for href in re.findall(r'href="([^"]+)"', html):
            m = rx.search(href)
            if m and "new_form" not in href.lower():
                url = href if href.startswith("http") else "https://www.dol.gov" + "/" + href.lstrip("/")
                found[(int(m.group(1)), int(m.group(2)))] = url
        if found:
            fy, q = max(found)
            return found[(fy, q)], f"FY{fy} Q{q}"
        log("  DOL page had no matching links; guessing file locations")
    except requests.RequestException as e:
        log(f"  DOL page not reachable ({e}); guessing file locations")

    today = dt.date.today()
    fy_now = today.year + (1 if today.month >= 10 else 0)
    for fy in range(fy_now, fy_now - 3, -1):
        for q in (4, 3, 2, 1):
            name = pattern.format(fy=fy, q=q)
            for folder in ("https://www.dol.gov/media/", base):
                try:
                    with requests.get(folder + name, headers=DOL_HEADERS, timeout=30, stream=True) as r:
                        if r.status_code == 200:
                            return folder + name, f"FY{fy} Q{q}"
                except requests.RequestException:
                    continue
    raise RuntimeError(f"Could not find the latest file for {pattern}")


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo))


# ---------------------------------------------------------------- H-1B (LCA)
def load_lca(path: Path, socs: set[str]) -> dict:
    log("  LCA 파일 읽는 중 (수 분 걸립니다)")
    keep = ("CASE_STATUS", "VISA_CLASS", "SOC_CODE", "EMPLOYER_NAME", "WORKSITE_STATE",
            "WAGE_RATE_OF_PAY_FROM", "WAGE_UNIT_OF_PAY", "FULL_TIME_POSITION")
    df = pd.read_excel(path, dtype=str, engine="openpyxl",
                       usecols=lambda c: any(str(c).upper().strip().startswith(k) for k in keep))
    c_status = pick(df, "CASE_STATUS")
    c_visa = pick(df, "VISA_CLASS")
    c_soc = pick(df, "SOC_CODE")
    c_emp = pick(df, "EMPLOYER_NAME")
    c_state = pick(df, "WORKSITE_STATE", "WORKSITE_STATE_1")
    c_wage = pick(df, "WAGE_RATE_OF_PAY_FROM", "WAGE_RATE_OF_PAY_FROM_1")
    c_unit = pick(df, "WAGE_UNIT_OF_PAY", "WAGE_UNIT_OF_PAY_1")
    c_ft = pick(df, "FULL_TIME_POSITION")
    missing = [n for n, c in [("CASE_STATUS", c_status), ("SOC_CODE", c_soc),
                              ("EMPLOYER_NAME", c_emp), ("WAGE", c_wage)] if c is None]
    if missing:
        raise RuntimeError(f"LCA 열을 찾지 못했습니다: {missing}\n실제 열: {list(df.columns)[:40]}")

    df = df[df[c_status].str.strip().str.lower() == "certified"]
    if c_visa:
        df = df[df[c_visa].str.strip() == "H-1B"]
    if c_ft:
        df = df[df[c_ft].str.strip().str.upper() == "Y"]
    df = df.assign(_soc=df[c_soc].map(norm_soc))
    df = df[df["_soc"].isin(socs)]

    wage = pd.to_numeric(df[c_wage].str.replace(r"[$,]", "", regex=True), errors="coerce")
    unit = df[c_unit].str.strip().str.lower() if c_unit else "year"
    mult = unit.map(WAGE_MULT) if c_unit else 1
    df = df.assign(_wage=wage * mult)

    out = {}
    for soc, g in df.groupby("_soc"):
        wages = [w for w in g["_wage"].dropna() if 20_000 <= w <= 1_000_000]
        emp = Counter(g[c_emp].str.strip().str.upper())
        emp_wages = defaultdict(list)
        for e, w in zip(g[c_emp].str.strip().str.upper(), g["_wage"]):
            if pd.notna(w) and 20_000 <= w <= 1_000_000:
                emp_wages[e].append(w)
        out[soc] = {
            "filings": int(len(g)),
            "wage_p25": pct(wages, 0.25),
            "wage_median": pct(wages, 0.5),
            "wage_p75": pct(wages, 0.75),
            "top_employers": [
                {"name": e, "filings": n,
                 "wage_median": round(median(emp_wages[e])) if emp_wages[e] else None}
                for e, n in emp.most_common(10)
            ],
            "top_states": [{"state": s, "filings": n}
                           for s, n in Counter(g[c_state].str.strip()).most_common(5)] if c_state else [],
        }
    return out


# ---------------------------------------------------------------- 영주권 (PERM)
def pick_like(df: pd.DataFrame, *groups: tuple[str, ...]) -> str | None:
    """열 이름에 주어진 단어가 모두 들어간 첫 열 (양식이 바뀌어도 찾기 위한 보조 수단)."""
    for words in groups:
        for c in df.columns:
            name = str(c).upper()
            if all(w in name for w in words):
                return c
    return None


def annualize(wage: pd.Series, unit: pd.Series | None) -> pd.Series:
    w = pd.to_numeric(wage.astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    if unit is None:
        return w
    u = unit.astype(str).str.strip().str.lower()
    u = u.replace({"yr": "year", "hr": "hour", "mth": "month", "wk": "week", "bi": "bi-weekly"})
    return w * u.map(WAGE_MULT)


def load_perm(path: Path, socs: set[str]) -> tuple[dict, list]:
    log("  PERM 파일 읽는 중")
    words = ("STATUS", "SOC", "EMP", "DATE", "WAGE", "STATE", "CITIZEN", "COUNTRY")
    df = pd.read_excel(path, dtype=str, engine="openpyxl",
                       usecols=lambda c: any(w in str(c).upper() for w in words))
    c_status = pick(df, "CASE_STATUS")
    c_soc = pick(df, "PW_SOC_CODE", "PWD_SOC_CODE", "SOC_CODE", "PW_SOC", "JOB_SOC_CODE") \
        or pick_like(df, ("SOC", "CODE"))
    c_emp = pick(df, "EMPLOYER_NAME", "EMP_BUSINESS_NAME", "EMP_NAME") or pick_like(df, ("EMP", "NAME"))
    c_recv = pick(df, "RECEIVED_DATE", "CASE_RECEIVED_DATE")
    c_dec = pick(df, "DECISION_DATE")
    c_wage = pick(df, "WAGE_OFFER_FROM_9089", "WAGE_OFFER_FROM", "JOB_OPP_WAGE_FROM", "WAGE_OFFERED_FROM") \
        or pick_like(df, ("WAGE", "OFFER", "FROM"), ("JOB_OPP", "WAGE", "FROM"))
    c_unit = pick(df, "WAGE_OFFER_UNIT_OF_PAY_9089", "WAGE_OFFER_UNIT_OF_PAY", "JOB_OPP_WAGE_PER",
                  "WAGE_UNIT_OF_PAY") or pick_like(df, ("WAGE", "OFFER", "UNIT"), ("JOB_OPP", "WAGE", "PER"))
    c_state = pick(df, "WORKSITE_STATE", "PRIMARY_WORKSITE_STATE", "JOB_INFO_WORK_STATE") \
        or pick_like(df, ("WORKSITE", "STATE"))
    c_country = pick(df, "COUNTRY_OF_CITIZENSHIP", "FW_INFO_CITIZENSHIP_COUNTRY", "FOREIGN_WORKER_CITIZENSHIP") \
        or pick_like(df, ("CITIZENSHIP",))
    if not (c_status and c_soc):
        raise RuntimeError(f"PERM 열을 찾지 못했습니다. 실제 열: {list(df.columns)}")
    log(f"  사용한 열: 직종={c_soc}, 회사={c_emp}, 임금={c_wage}/{c_unit}, 주={c_state}, 국적={c_country}")

    df = df.assign(_soc=df[c_soc].map(norm_soc))
    df = df[df["_soc"].isin(socs)].copy()
    df["_cert"] = df[c_status].str.strip().str.lower().str.startswith("certified")
    df["_emp"] = df[c_emp].str.strip().str.upper() if c_emp else ""
    df["_wage"] = annualize(df[c_wage], df[c_unit] if c_unit else None) if c_wage else float("nan")
    if c_recv and c_dec:
        df["_days"] = (pd.to_datetime(df[c_dec], errors="coerce")
                       - pd.to_datetime(df[c_recv], errors="coerce")).dt.days

    out = {}
    for soc, g in df.groupby("_soc"):
        cert = g[g["_cert"]]
        wages = [w for w in cert["_wage"].dropna() if 15_000 <= w <= 1_000_000]
        emp_n = Counter(cert["_emp"])
        emp_w = defaultdict(list)
        for e, w in zip(cert["_emp"], cert["_wage"]):
            if pd.notna(w) and 15_000 <= w <= 1_000_000:
                emp_w[e].append(w)
        item = {
            "decisions": int(len(g)),
            "certified": int(len(cert)),
            "cert_rate": round(len(cert) / len(g) * 100, 1) if len(g) else None,
            "wage_p25": pct(wages, 0.25), "wage_median": pct(wages, 0.5), "wage_p75": pct(wages, 0.75),
            "top_employers": [{"name": e, "certified": n,
                               "wage_median": round(median(emp_w[e])) if emp_w[e] else None}
                              for e, n in emp_n.most_common(15)],
            "top_states": [{"state": st, "certified": n}
                           for st, n in Counter(cert[c_state].str.strip()).most_common(6)] if c_state else [],
        }
        if "_days" in g:
            item["days_median"] = pct([x for x in cert["_days"].dropna() if 0 < x < 2000], 0.5)
        if c_country:
            countries = Counter(cert[c_country].dropna().str.strip().str.title())
            item["top_countries"] = [{"country": k, "certified": n} for k, n in countries.most_common(6)]
            item["korea_certified"] = int(sum(n for k, n in countries.items() if "KOREA" in k.upper()
                                              and "NORTH" not in k.upper() and "DEMOCRATIC" not in k.upper()))
        out[soc] = item

    # 회사 색인: 이 사이트가 다루는 직종에서 영주권을 진행한 회사 전체
    index = []
    for emp, g in df.groupby("_emp"):
        if not emp:
            continue
        index.append({
            "n": emp,
            "c": int(g["_cert"].sum()),
            "d": int(len(g)),
            "s": [soc for soc, _ in Counter(g["_soc"]).most_common(3)],
            "st": Counter(g[c_state].str.strip()).most_common(1)[0][0] if c_state else "",
        })
    index.sort(key=lambda x: -x["d"])
    return out, index[:5000]


# ---------------------------------------------------------------- 비자 블루틴
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def parse_vb_date(v: str) -> str:
    v = str(v).strip().upper()
    if v in ("C", "U"):
        return v
    try:
        return dt.datetime.strptime(v, "%d%b%y").date().isoformat()
    except ValueError:
        return v


def fetch_visa_bulletin(pattern: str, history_path: Path) -> dict:
    """이번 달과 다음 달 비자 블루틴에서 EB-3 숙련(3rd)과 비숙련(Other Workers) 날짜를 가져옵니다."""
    today = dt.date.today()
    candidates = []
    for add in (1, 0):
        m = (today.month - 1 + add) % 12 + 1
        y = today.year + (1 if today.month + add > 12 else 0)
        fy = y + (1 if m >= 10 else 0)
        candidates.append((y, m, pattern.format(fy=fy, month=MONTHS[m - 1], year=y)))

    hist = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {"history": []}
    for y, m, url in candidates:
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.status_code != 200:
            continue
        tables = [t for t in pd.read_html(io.StringIO(r.text))
                  if "employment" in " ".join(map(str, t.columns)).lower() + str(t.iloc[:1].values).lower()]
        if len(tables) < 2:
            log(f"  블루틴 표를 찾지 못함: {url}")
            continue

        def row(t, label):
            t = t.copy()
            if "employment" in str(t.iloc[0, 0]).lower():
                t.columns, t = t.iloc[0], t.iloc[1:]
            for _, rr in t.iterrows():
                if str(rr.iloc[0]).strip().lower() == label:
                    return parse_vb_date(rr.iloc[1])  # 둘째 열 = All Chargeability (한국 해당)
            return None

        entry = {"month": f"{y}-{m:02d}", "url": url,
                 "eb3_final": row(tables[0], "3rd"), "ew_final": row(tables[0], "other workers"),
                 "eb3_filing": row(tables[1], "3rd"), "ew_filing": row(tables[1], "other workers")}
        h = [x for x in hist["history"] if x["month"] != entry["month"]] + [entry]
        h.sort(key=lambda x: x["month"])
        log(f"  비자 블루틴 {entry['month']}: EB-3 {entry['eb3_final']}, 비숙련 {entry['ew_final']}")
        return {"current": entry, "history": h[-36:]}
    log("  비자 블루틴을 가져오지 못해 이전 기록을 유지합니다")
    return hist if hist.get("history") else {"current": None, "history": []}


# ---------------------------------------------------------------- College Scorecard
def load_scorecard(path: Path, cip4s: set[str]) -> dict:
    log("  College Scorecard 읽는 중")
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(io.BytesIO(z.read(name)), dtype=str, low_memory=False)
    c_earn1 = pick(df, "EARN_MDN_1YR", "EARN_MDN_HI_1YR")
    c_earn4 = pick(df, "EARN_MDN_4YR", "EARN_MDN_5YR", "EARN_MDN_HI_2YR")
    c_cnt = pick(df, "EARN_COUNT_WNE_1YR", "EARN_COUNT_WNE_HI_1YR", "IPEDSCOUNT2", "IPEDSCOUNT1")
    df = df.assign(_cip=df["CIPCODE"].str.zfill(4))
    df = df[df["_cip"].isin(cip4s) & df["CREDLEV"].isin(["3", "5"])]

    out = defaultdict(lambda: {"3": [], "5": []})
    for _, r in df.iterrows():
        e1 = pd.to_numeric(r.get(c_earn1), errors="coerce") if c_earn1 else None
        if pd.isna(e1):
            continue
        e4 = pd.to_numeric(r.get(c_earn4), errors="coerce") if c_earn4 else None
        out[r["_cip"]][r["CREDLEV"]].append({
            "school": r["INSTNM"],
            "unitid": r["UNITID"],
            "earn_1yr": int(e1),
            "earn_later": None if e4 is None or pd.isna(e4) else int(e4),
            "count": int(pd.to_numeric(r.get(c_cnt), errors="coerce") or 0) if c_cnt else None,
        })
    result = {}
    for cip, levels in out.items():
        result[cip] = {}
        for lv, rows in levels.items():
            rows.sort(key=lambda x: x["earn_1yr"], reverse=True)
            result[cip][lv] = {
                "programs": len(rows),
                "median_earn_1yr": pct([x["earn_1yr"] for x in rows], 0.5),
                "top": rows[:20],
            }
    return result


# ---------------------------------------------------------------- 실행
def local_dol_file(folder: Path | None, prefix: str) -> tuple[Path, str] | None:
    """Newest DOL disclosure file already downloaded into a folder (for runs from a home PC)."""
    if not folder or not folder.exists():
        return None
    best = None
    for f in folder.glob(f"{prefix}*.xlsx"):
        m = re.search(r"FY(\d{4})_Q([1-4])", f.name)
        if m and "new_form" not in f.name.lower():
            key = (int(m.group(1)), int(m.group(2)))
            if best is None or key > best[0]:
                best = (key, f)
    return (best[1], f"FY{best[0][0]} Q{best[0][1]}") if best else None


def save(name: str, obj, compact=False):
    (OUT / f"{name}.json").write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":") if compact else None), encoding="utf-8")


def main(argv: list[str]) -> int:
    """Each part is collected on its own, so one blocked site doesn't stop the rest.

    --dol-dir DIR   use LCA/PERM xlsx files already downloaded into DIR (dol.gov blocks cloud servers)
    """
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    src = cfg["sources"]
    RAW.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    dol_dir = Path(argv[argv.index("--dol-dir") + 1]).expanduser() if "--dol-dir" in argv else None

    socs = {s for m in cfg["majors"] for s in m["soc"]} | {j["soc"] for j in cfg.get("jobs", [])}
    cip4s = {m["cip4"] for m in cfg["majors"]}
    meta_path = OUT / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    failed = []

    def dol_source(prefix, pattern):
        local = local_dol_file(dol_dir, prefix)
        if local:
            log(f"  using local file {local[0]}")
            return local
        url, period = find_latest(src["dol_base"], pattern)
        return download(url, RAW / Path(url).name), period

    log("1/4 H-1B (LCA)")
    try:
        path, period = dol_source("LCA_Disclosure_Data_FY", src["lca_pattern"])
        save("lca", load_lca(path, socs))
        meta["lca"] = {"period": period, "file": path.name}
    except Exception as e:  # noqa: BLE001
        log(f"  H-1B failed: {e}")
        failed.append("lca")

    log("2/4 Green card (PERM)")
    try:
        path, period = dol_source("PERM_Disclosure_Data_FY", src["perm_pattern"])
        perm, employers = load_perm(path, socs)
        save("perm", perm)
        save("employers", employers, compact=True)
        meta["perm"] = {"period": period, "file": path.name}
    except Exception as e:  # noqa: BLE001
        log(f"  PERM failed: {e}")
        failed.append("perm")

    log("3/4 Visa Bulletin")
    try:
        vb = fetch_visa_bulletin(src["visa_bulletin_pattern"], OUT / "visa_bulletin.json")
        if vb.get("current"):
            save("visa_bulletin", vb)
        else:
            failed.append("visa_bulletin")
    except Exception as e:  # noqa: BLE001
        log(f"  Visa Bulletin failed: {e}")
        failed.append("visa_bulletin")

    log("4/4 College Scorecard")
    try:
        sc_url = src["scorecard_fos_zip"]
        save("scorecard", load_scorecard(download(sc_url, RAW / Path(sc_url).name), cip4s))
        meta["scorecard"] = {"url": sc_url}
    except Exception as e:  # noqa: BLE001
        log(f"  Scorecard failed: {e}")
        failed.append("scorecard")

    meta["generated"] = dt.date.today().isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Done. Failed parts: {', '.join(failed) or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
