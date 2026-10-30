"""Related Naver blog posts for the Korean pages (title, blogger, date, short snippet, link only).

Needs NAVER_CLIENT_ID / NAVER_CLIENT_SECRET (developers.naver.com, 검색 API). Without them it exits quietly.
Writes data/live/blogs.json: {"country:ca": [...], "visa:ca:pgwp": [...], "updated": "..."}
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "live" / "blogs.json"
API = "https://openapi.naver.com/v1/search/blog.json"

NAMES = {"us": "미국", "ca": "캐나다", "uk": "영국", "au": "호주", "nz": "뉴질랜드", "de": "독일", "jp": "일본", "sg": "싱가포르"}
COUNTRY_QUERIES = ["{n} 워킹홀리데이 후기", "{n} 취업비자 후기", "{n} 영주권 후기"]
# skip obvious promotion: agency sales posts and sponsored reviews
AD_WORDS = ["상담", "문의", "카톡", "오픈채팅", "이벤트", "협찬", "원고료", "제공받", "할인", "수수료 무료", "전문 유학원", "이주공사 추천"]
KEEP_PER_PAGE = 5
MAX_AGE_DAYS = 730


def clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def search(q: str, cid: str, secret: str) -> list[dict]:
    r = requests.get(API, params={"query": q, "display": 30, "sort": "sim"}, timeout=20,
                     headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret})
    r.raise_for_status()
    out = []
    cutoff = (dt.date.today() - dt.timedelta(days=MAX_AGE_DAYS)).strftime("%Y%m%d")
    for it in r.json().get("items", []):
        title, desc = clean(it.get("title")), clean(it.get("description"))
        text = title + " " + desc
        if any(w in text for w in AD_WORDS):
            continue
        if (it.get("postdate") or "0") < cutoff:
            continue
        out.append({"t": title, "d": desc[:110], "u": it.get("link"), "b": clean(it.get("bloggername")),
                    "dt": it.get("postdate", "")})
    return out


def pick(queries: list[str], cid: str, secret: str) -> list[dict]:
    seen, res = set(), []
    lists = []
    for q in queries:
        try:
            lists.append(search(q, cid, secret))
        except Exception as e:  # one failed query should not stop the rest
            print(f"  '{q}' 실패: {e}")
            lists.append([])
        time.sleep(0.12)
    # interleave the query results so each page shows a mix (working holiday, visas, PR)
    for i in range(30):
        for lst in lists:
            if i < len(lst) and lst[i]["u"] not in seen:
                seen.add(lst[i]["u"])
                res.append(lst[i])
    return res[:KEEP_PER_PAGE]


def main() -> int:
    cid, secret = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    if not (cid and secret):
        print("NAVER_CLIENT_ID/SECRET 없음: 블로그 후기 수집을 건너뜁니다")
        return 0
    visas = yaml.safe_load((ROOT / "data" / "visas.yaml").read_text(encoding="utf-8"))["countries"]
    out: dict = {}
    for c, n in NAMES.items():
        out[f"country:{c}"] = pick([q.format(n=n) for q in COUNTRY_QUERIES], cid, secret)
        for v in visas.get(c, {}).get("visas", []):
            code = v.get("code_ko") or v["code"]
            out[f"visa:{c}:{v['id']}"] = pick([f"{n} {code} 비자 후기", f"{n} {code} 비자"], cid, secret)
        print(f"  {n}: 완료")
    out["updated"] = dt.date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"블로그 후기 {sum(len(v) for k, v in out.items() if k != 'updated')}건 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
