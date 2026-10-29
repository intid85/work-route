"""Build the static site (site/) from the summary JSON in data/.

    python scripts/build_site.py            # data/live if present, otherwise sample data
    python scripts/build_site.py --sample   # force sample data
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "Washington, D.C.", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico", "GU": "Guam",
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------- filters
def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def money(v):
    return f"${int(v):,}" if _isnum(v) else "–"


def num(v):
    return f"{int(v):,}" if _isnum(v) else "–"


def hourly(v):
    return f"${v / 2080:,.2f}" if _isnum(v) else "–"


def vbdate(v):
    """Visa bulletin date in plain English."""
    if not v:
        return "No data"
    if v == "C":
        return "Current"
    if v == "U":
        return "Unavailable"
    try:
        d = dt.date.fromisoformat(v)
        return f"{MONTHS[d.month - 1][:3]} {d.day}, {d.year}"
    except ValueError:
        return v


def month_name(ym):
    try:
        y, m = ym.split("-")
        return f"{MONTHS[int(m) - 1]} {y}"
    except (ValueError, AttributeError):
        return ym


def wait_gap(bulletin_month, v):
    """Gap between the bulletin month and the cutoff date: roughly how long people now being approved waited."""
    try:
        y, m = map(int, bulletin_month.split("-"))
        d = dt.date.fromisoformat(v)
    except (ValueError, AttributeError, TypeError):
        return None
    months = (y - d.year) * 12 + (m - d.month)
    yrs, mos = divmod(months, 12)
    if yrs == 0:
        return f"about {mos} months"
    return f"about {yrs} yr {mos} mo" if mos else f"about {yrs} years"


# ---------------------------------------------------------------- Korean edition
STATES_KO = {
    "AL": "앨라배마", "AK": "알래스카", "AZ": "애리조나", "AR": "아칸소", "CA": "캘리포니아", "CO": "콜로라도",
    "CT": "코네티컷", "DE": "델라웨어", "DC": "워싱턴 D.C.", "FL": "플로리다", "GA": "조지아", "HI": "하와이",
    "ID": "아이다호", "IL": "일리노이", "IN": "인디애나", "IA": "아이오와", "KS": "캔자스", "KY": "켄터키",
    "LA": "루이지애나", "ME": "메인", "MD": "메릴랜드", "MA": "매사추세츠", "MI": "미시간", "MN": "미네소타",
    "MS": "미시시피", "MO": "미주리", "MT": "몬태나", "NE": "네브래스카", "NV": "네바다", "NH": "뉴햄프셔",
    "NJ": "뉴저지", "NM": "뉴멕시코", "NY": "뉴욕", "NC": "노스캐롤라이나", "ND": "노스다코타", "OH": "오하이오",
    "OK": "오클라호마", "OR": "오리건", "PA": "펜실베이니아", "RI": "로드아일랜드", "SC": "사우스캐롤라이나",
    "SD": "사우스다코타", "TN": "테네시", "TX": "텍사스", "UT": "유타", "VT": "버몬트", "VA": "버지니아",
    "WA": "워싱턴", "WV": "웨스트버지니아", "WI": "위스콘신", "WY": "와이오밍", "PR": "푸에르토리코", "GU": "괌",
}
PROV_KO = {
    "Alberta": "앨버타", "British Columbia": "브리티시컬럼비아", "Manitoba": "매니토바", "New Brunswick": "뉴브런즈윅",
    "Newfoundland and Labrador": "뉴펀들랜드 래브라도", "Northwest Territories": "노스웨스트 준주", "Nova Scotia": "노바스코샤",
    "Nunavut": "누나부트", "Ontario": "온타리오", "Prince Edward Island": "프린스에드워드아일랜드", "Quebec": "퀘벡",
    "Saskatchewan": "서스캐처원", "Yukon": "유콘",
    "Employers carrying on business in Canada with Head Office outside of Canada": "본사가 해외인 회사",
}
AU_STATES_KO = {
    "New South Wales": "뉴사우스웨일스", "Victoria": "빅토리아", "Queensland": "퀸즐랜드", "Western Australia": "서호주",
    "South Australia": "남호주", "Tasmania": "태즈메이니아", "Northern Territory": "노던 준주",
    "Australian Capital Territory": "수도 준주",
}
COUNTRIES_KO = {
    "India": "인도", "Mexico": "멕시코", "Philippines": "필리핀", "China": "중국", "Guatemala": "과테말라",
    "South Korea": "한국", "Korea, South": "한국", "Korea, Republic Of": "한국", "Republic Of Korea": "한국",
    "Vietnam": "베트남", "Brazil": "브라질", "United Kingdom": "영국", "South Africa": "남아공",
    "Ireland, Republic of": "아일랜드", "Ireland": "아일랜드", "Nepal": "네팔", "Sri Lanka": "스리랑카",
    "China, Peoples Republic of (excl SARs)": "중국", "Japan": "일본", "Fiji": "피지", "Indonesia": "인도네시아",
    "Thailand": "태국", "Pakistan": "파키스탄", "Bangladesh": "방글라데시", "Colombia": "콜롬비아",
    "Zimbabwe": "짐바브웨", "New Zealand": "뉴질랜드", "Canada": "캐나다", "France": "프랑스", "Germany": "독일",
    "Honduras": "온두라스", "El Salvador": "엘살바도르", "Jamaica": "자메이카", "Nigeria": "나이지리아",
    "Kenya": "케냐", "Ghana": "가나", "Malaysia": "말레이시아", "Taiwan": "대만", "Myanmar": "미얀마",
    "Cambodia": "캄보디아", "Mongolia": "몽골", "Laos": "라오스", "Uzbekistan": "우즈베키스탄",
}
STREAMS_KO = {"Low Wage": "저임금", "High Wage": "고임금", "Primary Agriculture": "1차 농업",
              "Permanent Resident Only": "영주권 전용", "Global Talent": "글로벌 인재"}
AU_STREAMS_KO = {"Core Skills": "Core Skills(핵심 기술)", "Labour Agreement": "노동 협약", "Medium-term": "중기(구 TSS)",
                 "Short-term": "단기(구 TSS)", "Specialist Skills": "Specialist Skills(전문 기술)"}
INDUSTRY_KO = {"Manufacturing": "제조업", "Construction": "건설업", "Mining": "광업",
               "Accommodation and Food Services": "숙박·음식업", "Health Care and Social Assistance": "보건·사회복지",
               "Agriculture, Forestry and Fishing": "농림어업", "Other Services": "기타 서비스",
               "Transport, Postal and Warehousing": "운송·창고", "Retail Trade": "소매업",
               "Wholesale Trade": "도매업", "Administrative and Support Services": "사업 지원 서비스"}


def kdate(v):
    if not v:
        return "자료 없음"
    if v == "C":
        return "대기 없음"
    if v == "U":
        return "발급 중단"
    try:
        d = dt.date.fromisoformat(v)
        return f"{d.year}년 {d.month}월 {d.day}일"
    except ValueError:
        return v


def kmonth(ym):
    try:
        y, m = ym.split("-")
        return f"{y}년 {int(m)}월"
    except (ValueError, AttributeError):
        return ym


def kgap(v, bulletin_month):
    try:
        y, m = map(int, bulletin_month.split("-"))
        d = dt.date.fromisoformat(v)
    except (ValueError, AttributeError, TypeError):
        return None
    months = (y - d.year) * 12 + (m - d.month)
    return f"약 {months // 12}년 {months % 12}개월" if months >= 12 else f"약 {months}개월"


# ---------------------------------------------------------------- page data
def load(d: Path, name: str, default=None):
    p = d / f"{name}.json"
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def build_major(m: dict, lca: dict, perm: dict, sc: dict) -> dict:
    occs = [{"soc": soc, "name": name, "lca": lca.get(soc, {}), "perm": perm.get(soc, {})}
            for soc, name in m["soc"].items()]
    perm_dec = sum(o["perm"].get("decisions", 0) for o in occs)
    perm_cert = sum(o["perm"].get("certified", 0) for o in occs)
    days = [o["perm"].get("days_median") for o in occs if o["perm"].get("days_median")]
    school = sc.get(m["cip4"], {})
    return {**m, "occs": occs, "primary": occs[0],
            "h1b_total": sum(o["lca"].get("filings", 0) for o in occs),
            "h1b_median": occs[0]["lca"].get("wage_median"),
            "perm_cert": perm_cert,
            "perm_rate": round(perm_cert / perm_dec * 100, 1) if perm_dec else None,
            "perm_days": days[0] if days else None,
            "opt_months": 36 if m["stem"] else 12,
            "ba": school.get("3", {}), "ma": school.get("5", {})}


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    live, sample = ROOT / "data" / "live", ROOT / "data" / "sample"
    if not (sample / "meta.json").exists():
        import make_sample
        make_sample.main()
    force_sample = "--sample" in sys.argv

    def data(name, default=None):
        """Live data when it has been collected, otherwise the sample file."""
        if not force_sample and (live / f"{name}.json").exists():
            return load(live, name, default)
        return load(sample, name, default)

    us_live = not force_sample and (live / "perm.json").exists()
    meta = dict(data("meta") or {})
    meta["sample"] = not us_live
    meta["sample_parts"] = [n for n, f in (("US", "perm"), ("Canada", "ca"), ("UK", "uk"), ("Australia", "au"), ("Japan", "jp"))
                            if force_sample or not (live / f"{f}.json").exists()]
    lca, perm, sc = data("lca", {}), data("perm", {}), data("scorecard", {})
    vb = data("visa_bulletin", {"current": None, "history": []})
    ca = data("ca")
    uk = data("uk")
    au = data("au")
    jp = data("jp")
    sg = yaml.safe_load((ROOT / "data" / "sg.yaml").read_text(encoding="utf-8"))
    d = live
    korea_e9 = load(ROOT / "data", "korea_e9") or load(sample, "korea_e9")
    korea = yaml.safe_load((ROOT / "data" / "korea.yaml").read_text(encoding="utf-8"))
    pw = yaml.safe_load((ROOT / "data" / "pathways.yaml").read_text(encoding="utf-8"))
    links = {"us": "../us/index.html", "ca": "../ca/index.html", "uk": "../uk/index.html",
             "au": "../au/index.html", "jp": "../jp/index.html", "sg": "../sg/index.html", "kr": "../korea/index.html"}
    order = ["us", "ca", "uk", "au", "jp", "sg", "kr"]
    pw["countries"].sort(key=lambda p: order.index(p["code"]))
    pathways = []
    for p in pw["countries"]:
        if (p["code"] == "ca" and not ca) or (p["code"] == "uk" and not uk) or (p["code"] == "au" and not au):
            continue
        pathways.append({**p, "link": links[p["code"]]})
    path_by = {p["code"]: p for p in pathways}
    pw_ko = yaml.safe_load((ROOT / "data" / "pathways_ko.yaml").read_text(encoding="utf-8"))
    pw_ko["countries"].sort(key=lambda p: order.index(p["code"]))
    pathways_ko = [{**p, "link": links[p["code"]]} for p in pw_ko["countries"]
                   if not ((p["code"] == "ca" and not ca) or (p["code"] == "uk" and not uk) or (p["code"] == "au" and not au))]
    path_ko = {p["code"]: p for p in pathways_ko}
    names_ko = {"US": "미국", "Canada": "캐나다", "UK": "영국", "Australia": "호주", "Japan": "일본"}
    visas_meta = yaml.safe_load((ROOT / "data" / "visas.yaml").read_text(encoding="utf-8"))
    visas_by = {code: {**v, "code": code} for code, v in visas_meta["countries"].items()}

    majors = [build_major(m, lca, perm, sc) for m in cfg["majors"]]
    jobs = []
    for j in cfg["jobs"]:
        jobs.append({**j, "perm": perm.get(j["soc"], {}),
                     "ca": (ca or {}).get("by_noc", {}).get(j.get("noc") or "", {}),
                     "au": (au or {}).get("by_job", {}).get(j["slug"], {})})
    groups: dict[str, list] = {}
    for j in jobs:
        groups.setdefault(j["group"], []).append(j)

    groups_ko: dict[str, list] = {}
    for j in jobs:
        groups_ko.setdefault(j.get("group_ko", j["group"]), []).append(j)

    soc_names = {j["soc"]: j["name"] for j in jobs}
    for m in cfg["majors"]:
        for soc, name in m["soc"].items():
            soc_names.setdefault(soc, name)
    noc_names = {j["noc"]: j["name"] for j in jobs if j.get("noc")}

    site = dict(cfg["site"])
    if site.get("domain"):
        site["base_url"] = f"https://{site['domain']}"
    site["base_url"] = site["base_url"].rstrip("/")

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)
    env.filters.update(money=money, num=num, hourly=hourly, vbdate=vbdate, month_name=month_name,
                       state=lambda s: STATES.get(s, s), kdate=kdate, kmonth=kmonth, kgap=kgap,
                       kstate=lambda s: STATES_KO.get(s, s), kprov=lambda s: PROV_KO.get(s, s),
                       kaustate=lambda s: AU_STATES_KO.get(s, s), kcountry=lambda s: COUNTRIES_KO.get(s, s),
                       kstream=lambda s: STREAMS_KO.get(s, s), kaustream=lambda s: AU_STREAMS_KO.get(s, s),
                       kindustry=lambda s: INDUSTRY_KO.get(s, s))
    env.globals["wait_gap"] = wait_gap
    ctx = {"site": site, "meta": meta, "majors": majors, "jobs": jobs, "groups": groups, "vb": vb,
           "ca": ca, "uk": uk, "au": au, "jp": jp, "sg": sg, "groups_ko": groups_ko,
           "jp_field_name": {f["ja"]: f for f in (jp or {}).get("fields", [])}, "visas_meta": visas_meta, "visas_by": visas_by, "korea": korea, "korea_e9": korea_e9, "build_date": dt.date.today().isoformat()}

    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "static", SITE / "static")
    pages = []

    ko_pages = {"index.html", "pathways/index.html", "us/index.html", "us/employers/index.html", "jp/index.html", "sg/index.html",
                "us/visa-bulletin/index.html", "ca/index.html", "ca/employers/index.html", "uk/index.html", "au/index.html"}
    ko_pages |= {f"us/jobs/{j['slug']}/index.html" for j in jobs} | {f"us/majors/{m['slug']}/index.html" for m in majors}
    ko_pages |= {f"ca/jobs/{j['slug']}/index.html" for j in jobs if j.get("noc") and ca}
    ko_pages |= {f"au/jobs/{j['slug']}/index.html" for j in jobs if j["au"]}

    def render(tpl: str, path: str, lang: str = "en", **extra):
        out = SITE / path
        out.parent.mkdir(parents=True, exist_ok=True)
        rel = "../" * path.count("/")
        if tpl == "404.html":
            rel = site["base_url"] + "/"
        page_path = "/" + path.removesuffix("index.html")
        if lang == "ko":
            twin = path.removeprefix("ko/")
            alt_path, alt_href = "/" + twin.removesuffix("index.html"), rel + twin
        elif path in ko_pages:
            alt_path, alt_href = "/ko/" + path.removesuffix("index.html"), rel + "ko/" + path
        else:
            alt_path = alt_href = None
        local = {"lang": lang, "page_path": page_path, "alt_path": alt_path, "alt_href": alt_href, "rel": rel,
                 "pathways": pathways_ko if lang == "ko" else pathways,
                 "pathways_as_of": pw_ko["as_of"] if lang == "ko" else pw["as_of"],
                 "sample_parts": [names_ko[n] for n in meta["sample_parts"]] if lang == "ko" else meta["sample_parts"]}
        out.write_text(env.get_template(tpl).render(**ctx, **local, **extra), encoding="utf-8")
        if path.endswith("index.html"):
            pages.append(page_path)

    def write_json(path: str, obj):
        (SITE / path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    render("home.html", "index.html", country=None)

    # United States
    render("pathways.html", "pathways/index.html", country="paths")
    render("us/index.html", "us/index.html", country="us", pw_path=path_by["us"])
    for j in jobs:
        render("us/job.html", f"us/jobs/{j['slug']}/index.html", country="us", j=j)
    for m in majors:
        render("us/major.html", f"us/majors/{m['slug']}/index.html", country="us", m=m)
    render("us/employers.html", "us/employers/index.html", country="us")
    render("us/bulletin.html", "us/visa-bulletin/index.html", country="us")
    emp = data("employers")
    if emp:
        write_json("static/us-employers.json", {"names": soc_names, "states": STATES, "rows": emp})

    # Canada
    if ca:
        render("ca/index.html", "ca/index.html", country="ca", pw_path=path_by["ca"])
        for j in jobs:
            if j.get("noc"):
                render("ca/job.html", f"ca/jobs/{j['slug']}/index.html", country="ca", j=j)
        render("ca/employers.html", "ca/employers/index.html", country="ca")
        ca_emp = data("ca_employers")
        if ca_emp:
            write_json("static/ca-employers.json", {"names": noc_names, "rows": ca_emp})

    # United Kingdom
    if uk:
        render("uk/index.html", "uk/index.html", country="uk", pw_path=path_by["uk"])
        uk_idx = data("uk_sponsors")
        if uk_idx:
            write_json("static/uk-sponsors.json", {"rows": uk_idx})

    # Australia
    if au:
        render("au/index.html", "au/index.html", country="au", pw_path=path_by["au"])
        for j in jobs:
            if j["au"]:
                render("au/job.html", f"au/jobs/{j['slug']}/index.html", country="au", j=j)

    # Japan and Singapore
    if jp:
        render("jp/index.html", "jp/index.html", country="jp", pw_path=path_by["jp"])
        render("ko/jp/index.html", "ko/jp/index.html", lang="ko", country="jp", pw_path=path_ko["jp"])
    render("sg/index.html", "sg/index.html", country="sg", pw_path=path_by["sg"])
    render("ko/sg/index.html", "ko/sg/index.html", lang="ko", country="sg", pw_path=path_ko["sg"])

    # South Korea
    render("korea/index.html", "korea/index.html", country="kr", pw_path=path_by["kr"])

    # Korean edition (Koreans going abroad; the Korea section is English only)
    render("ko/home.html", "ko/index.html", lang="ko", country=None)
    render("ko/pathways.html", "ko/pathways/index.html", lang="ko", country="paths")
    render("ko/us/index.html", "ko/us/index.html", lang="ko", country="us", pw_path=path_ko["us"])
    for j in jobs:
        render("ko/us/job.html", f"ko/us/jobs/{j['slug']}/index.html", lang="ko", country="us", j=j)
    for m in majors:
        render("ko/us/major.html", f"ko/us/majors/{m['slug']}/index.html", lang="ko", country="us", m=m)
    render("ko/us/employers.html", "ko/us/employers/index.html", lang="ko", country="us")
    render("ko/us/bulletin.html", "ko/us/visa-bulletin/index.html", lang="ko", country="us")
    if ca:
        render("ko/ca/index.html", "ko/ca/index.html", lang="ko", country="ca", pw_path=path_ko["ca"])
        for j in jobs:
            if j.get("noc"):
                render("ko/ca/job.html", f"ko/ca/jobs/{j['slug']}/index.html", lang="ko", country="ca", j=j)
        render("ko/ca/employers.html", "ko/ca/employers/index.html", lang="ko", country="ca")
    if uk:
        render("ko/uk/index.html", "ko/uk/index.html", lang="ko", country="uk", pw_path=path_ko["uk"])
    if au:
        render("ko/au/index.html", "ko/au/index.html", lang="ko", country="au", pw_path=path_ko["au"])
        for j in jobs:
            if j["au"]:
                render("ko/au/job.html", f"ko/au/jobs/{j['slug']}/index.html", lang="ko", country="au", j=j)

    render("about.html", "about/index.html", country=None)
    render("404.html", "404.html", country=None)
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{site['base_url']}{p}</loc><lastmod>{ctx['build_date']}</lastmod></url>\n" for p in pages)
        + "</urlset>\n", encoding="utf-8")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site['base_url']}/sitemap.xml\n", encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    if site.get("domain"):
        (SITE / "CNAME").write_text(site["domain"] + "\n")

    print(f"Built {len(pages)} pages; sample data used for: {', '.join(meta['sample_parts']) or 'nothing'} -> {SITE}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    sys.exit(main())
