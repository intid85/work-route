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
def money(v):
    return "No data" if v in (None, "") else f"${int(v):,}"


def num(v):
    return "–" if v in (None, "") else f"{int(v):,}"


def hourly(v):
    return "No data" if v in (None, "") else f"${v / 2080:,.2f}"


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
    meta["sample_parts"] = [n for n, f in (("US", "perm"), ("Canada", "ca"), ("UK", "uk"))
                            if force_sample or not (live / f"{f}.json").exists()]
    lca, perm, sc = data("lca", {}), data("perm", {}), data("scorecard", {})
    vb = data("visa_bulletin", {"current": None, "history": []})
    ca = data("ca")
    uk = data("uk")
    d = live
    korea_e9 = load(ROOT / "data", "korea_e9") or load(sample, "korea_e9")
    korea = yaml.safe_load((ROOT / "data" / "korea.yaml").read_text(encoding="utf-8"))

    majors = [build_major(m, lca, perm, sc) for m in cfg["majors"]]
    jobs = []
    for j in cfg["jobs"]:
        jobs.append({**j, "perm": perm.get(j["soc"], {}),
                     "ca": (ca or {}).get("by_noc", {}).get(j.get("noc") or "", {})})
    groups: dict[str, list] = {}
    for j in jobs:
        groups.setdefault(j["group"], []).append(j)

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
                       state=lambda s: STATES.get(s, s))
    env.globals["wait_gap"] = wait_gap
    ctx = {"site": site, "meta": meta, "majors": majors, "jobs": jobs, "groups": groups, "vb": vb,
           "ca": ca, "uk": uk, "korea": korea, "korea_e9": korea_e9, "build_date": dt.date.today().isoformat()}

    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "static", SITE / "static")
    pages = []

    def render(tpl: str, path: str, **extra):
        out = SITE / path
        out.parent.mkdir(parents=True, exist_ok=True)
        rel = "../" * path.count("/")
        if tpl == "404.html":
            rel = site["base_url"] + "/"
        page_path = "/" + path.removesuffix("index.html")
        out.write_text(env.get_template(tpl).render(**ctx, **extra, rel=rel, page_path=page_path), encoding="utf-8")
        if path.endswith("index.html"):
            pages.append(page_path)

    def write_json(path: str, obj):
        (SITE / path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    render("home.html", "index.html", country=None)

    # United States
    render("us/index.html", "us/index.html", country="us")
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
        render("ca/index.html", "ca/index.html", country="ca")
        for j in jobs:
            if j.get("noc"):
                render("ca/job.html", f"ca/jobs/{j['slug']}/index.html", country="ca", j=j)
        render("ca/employers.html", "ca/employers/index.html", country="ca")
        ca_emp = data("ca_employers")
        if ca_emp:
            write_json("static/ca-employers.json", {"names": noc_names, "rows": ca_emp})

    # United Kingdom
    if uk:
        render("uk/index.html", "uk/index.html", country="uk")
        uk_idx = data("uk_sponsors")
        if uk_idx:
            write_json("static/uk-sponsors.json", {"rows": uk_idx})

    # South Korea
    render("korea/index.html", "korea/index.html", country="kr")

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
