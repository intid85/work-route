"""'Which countries can I go to with my job?' — per-occupation verdicts for the home-page finder.

Each entry: {id, ko, en, alias, kind, countries: [{c, v, ko, en, ev_ko, ev_en, href}]}
v is 'yes' (a well-used route), 'maybe' (possible with conditions) or 'hard' (no realistic route today).
Rules reflect October 2026; update with the visa data in data/visas.yaml.
"""
from __future__ import annotations

ALIASES = {
    "welder": "용접 용접사 welding", "assembler": "생산직 공장 조립 factory", "machinery-mechanic": "기계 정비 설비 보전 maintenance",
    "meat-trimmer": "육가공 고기 meat", "meat-packer": "도축 포장 meat", "butcher": "정육 고기 butcher",
    "farmworker": "농장 축산 양계 농업 farm", "electrician": "전기 전기기사 전기공", "plumber": "배관 설비 plumbing",
    "construction-laborer": "건설 노가다 현장 막노동 construction", "auto-mechanic": "자동차 정비 카센터 mechanic",
    "cook": "요리 셰프 조리 주방 chef", "housekeeper": "호텔 하우스키핑 청소 객실", "warehouse": "물류 창고 택배 지게차 forklift",
    "registered-nurse": "간호 RN nurse", "nursing-assistant": "요양 간병 요양보호사 care worker caregiver",
    "15-1252": "개발자 프로그래머 코딩 IT developer programmer", "15-1211": "IT 시스템 분석", "15-1221": "AI 연구 연구원",
    "15-1253": "QA 테스터", "17-2061": "하드웨어 반도체", "17-2071": "전기 엔지니어", "17-2072": "전자 반도체",
    "17-2141": "기계 설계", "17-2041": "화학", "17-2112": "산업공학 생산관리", "17-2051": "토목 건설 엔지니어",
    "15-2051": "데이터 AI 머신러닝", "15-2041": "통계", "11-3021": "IT 매니저", "19-1042": "의학 연구 바이오",
    "19-1021": "생명 생화학 바이오", "13-2051": "금융 재무 애널리스트", "13-2011": "회계 회계사 세무 CPA",
    "19-3011": "경제", "13-1161": "마케팅 시장조사", "11-2021": "마케팅",
}

NAMES = {"us": ("미국", "United States"), "ca": ("캐나다", "Canada"), "uk": ("영국", "United Kingdom"),
         "au": ("호주", "Australia"), "nz": ("뉴질랜드", "New Zealand"), "de": ("독일", "Germany"),
         "jp": ("일본", "Japan"), "sg": ("싱가포르", "Singapore")}

SKILLED_TRADES = {"welder", "machinery-mechanic", "electrician", "plumber", "auto-mechanic", "cook", "butcher"}
NZ_TRADES = {"welder", "machinery-mechanic", "electrician", "plumber", "auto-mechanic"}


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, (int, float)) else "–"


def _row(c, v, ko, en, ev_ko="", ev_en="", href=None):
    return {"c": c, "v": v, "ko": ko, "en": en, "ev_ko": ev_ko, "ev_en": ev_en, "href": href or f"{c}/index.html"}


def trade_entry(j: dict, jp_fields: dict) -> dict:
    s = j["slug"]
    out = []
    # United States: employer-sponsored EB-3 green card (PERM)
    cert = (j.get("perm") or {}).get("certified") or 0
    v = "yes" if cert >= 50 else "maybe" if cert >= 5 else "hard"
    out.append(_row("us", v, "회사 스폰서 EB-3 영주권 (유학·취업비자 없이 바로)", "Employer-sponsored EB-3 green card, straight from abroad",
                    f"최근 9개월 영주권 인증 {_n(cert)}건", f"{_n(cert)} green card certifications in 9 months", f"us/jobs/{s}/index.html"))
    # Canada: LMIA work permit, then provincial nomination (Express Entry trades for skilled trades)
    pos = (j.get("ca") or {}).get("positions") or 0
    v = "yes" if pos >= 50 else "maybe" if pos > 0 else "hard"
    route_ko = "LMIA 취업비자 → Express Entry 기술직·주정부 추천" if s in SKILLED_TRADES else "LMIA 취업비자 → 주정부 추천(PNP)"
    route_en = "LMIA work permit, then Express Entry trades or a provincial nomination" if s in SKILLED_TRADES else "LMIA work permit, then a provincial nomination"
    out.append(_row("ca", v, route_ko, route_en, f"최근 분기 고용 승인 {_n(pos)}명", f"{_n(pos)} approved positions last quarter",
                    f"ca/jobs/{s}/index.html" if j.get("ca") else None))
    # United Kingdom: since 22 July 2025 new Skilled Worker visas need degree-level jobs
    if s == "registered-nurse":
        out.append(_row("uk", "yes", "Skilled Worker(간호사 면허 등록) → 영주권(ILR)", "Skilled Worker visa with NMC registration, then ILR"))
    else:
        out.append(_row("uk", "hard", "2025년 7월부터 학사 수준 직무만 신규 취업비자 (일부 부족직종만 예외)",
                        "Since July 2025 new Skilled Worker visas need degree-level jobs, with a few shortage exceptions"))
    # Australia: 482 employer sponsorship, then 186 after two years
    gr = (j.get("au") or {}).get("grants") or 0
    v = "yes" if gr >= 100 else "maybe" if gr > 0 else "hard"
    out.append(_row("au", v, "482 회사 스폰서 → 2년 뒤 186 영주권", "482 employer sponsorship, then the 186 PR visa after two years",
                    f"최근 1년 482 발급 {_n(gr)}건", f"{_n(gr)} 482 visas granted in a year", f"au/jobs/{s}/index.html" if j.get("au") else None))
    # New Zealand
    if s == "registered-nurse":
        out.append(_row("nz", "yes", "그린리스트 바로 영주권 직종", "Green List straight-to-residence role"))
    elif s in NZ_TRADES:
        out.append(_row("nz", "yes", "AEWV 취업비자 → 2026년 신설 기술직 영주권 경로", "AEWV, then the 2026 Trades and Technician residence pathway"))
    else:
        out.append(_row("nz", "maybe", "AEWV 취업은 가능, 영주권은 숙련 직종·경력 5년 필요", "AEWV work is possible; residence needs a skilled role and 5 years' experience"))
    # Germany
    if s == "registered-nurse":
        out.append(_row("de", "yes", "독일어 B1~B2 + 간호 자격 인정 → 숙련공 허가", "German B1–B2 and nursing recognition, then a skilled worker permit"))
    elif s in SKILLED_TRADES or s == "nursing-assistant":
        out.append(_row("de", "maybe", "독일어 B1 + 자격 인정 또는 아우스빌둥(유급 직업교육)", "German B1 plus recognition, or a paid Ausbildung"))
    else:
        out.append(_row("de", "hard", "비숙련 취업비자 없음, 아우스빌둥으로 기술을 배워야 함", "No visa for unskilled work; an Ausbildung is the way in"))
    # Japan: Specified Skilled Worker fields
    fields = [jp_fields[f] for f in j.get("jp_fields") or [] if f in jp_fields]
    if fields:
        w = sum(f.get("workers") or 0 for f in fields)
        k = sum(f.get("korea") or 0 for f in fields)
        names_ko = "·".join(f["ko"] for f in fields)
        names_en = ", ".join(f["en"] for f in fields)
        out.append(_row("jp", "yes", f"특정기능 ({names_ko}) → 2호 → 영주권", f"Specified Skilled Worker ({names_en}), then (ii) and PR",
                        f"해당 분야 현재 {_n(w)}명 근무, 한국인 {_n(k)}명", f"{_n(w)} workers in these fields, {_n(k)} Korean"))
    elif s == "registered-nurse":
        out.append(_row("jp", "maybe", "일본 간호사 국가시험(일본어) 합격 필요", "Must pass Japan's nursing exam in Japanese"))
    else:
        out.append(_row("jp", "hard", "해당 특정기능 분야 없음", "No matching Specified Skilled Worker field"))
    # Singapore
    if j.get("sg_pass") == "Work Permit":
        out.append(_row("sg", "maybe", "워크 퍼밋 취업 가능, 영주권은 S Pass로 올라가야", "Work Permit jobs; PR only after moving up to an S Pass"))
    else:
        out.append(_row("sg", "yes", f"{j.get('sg_pass')} → 영주권 신청", f"{j.get('sg_pass')}, then apply for PR"))
    return {"id": s, "ko": j["ko"], "en": j["name"], "alias": ALIASES.get(s, ""), "kind": "trade", "countries": out}


def degree_entry(soc: str, ko: str, en: str, major_slug: str, lca: dict, perm: dict) -> dict:
    f = (lca.get(soc) or {}).get("filings")
    c = (perm.get(soc) or {}).get("certified")
    rows = [
        _row("us", "yes", "H-1B 추첨 → 회사 스폰서 EB-2 영주권", "H-1B lottery, then an employer-sponsored EB-2 green card",
             f"H-1B {_n(f)}건, 영주권 인증 {_n(c)}건 (9개월)", f"{_n(f)} H-1B filings, {_n(c)} green card certifications in 9 months",
             f"us/majors/{major_slug}/index.html"),
        _row("ca", "yes", "Express Entry (학위·경력·영어 점수)", "Express Entry on degree, experience and English"),
        _row("uk", "yes", "Skilled Worker 스폰서 취업 → 영주권(ILR)", "Skilled Worker sponsorship, then ILR"),
        _row("au", "yes", "189·190 점수제 또는 482 회사 스폰서", "189/190 points visa or 482 employer sponsorship"),
        _row("nz", "yes", "숙련이민(SMC) 학위 점수로 영주권", "Skilled Migrant Category points from your degree"),
        _row("de", "yes", "EU 블루카드 (2026년 연봉 €50,700, 부족 분야 €45,934)", "EU Blue Card (€50,700 salary in 2026, €45,934 in shortage fields)"),
        _row("jp", "yes", "기술·인문지식·국제업무 → 고도전문직이면 1~3년 만에 영주권", "Engineer/Humanities visa; 1–3 years to PR as a Highly Skilled Professional"),
        _row("sg", "yes", "고용 패스(EP, 월 S$5,600 이상) → 영주권 신청", "Employment Pass (from S$5,600 a month), then apply for PR"),
    ]
    return {"id": soc, "ko": ko, "en": en, "alias": ALIASES.get(soc, ""), "kind": "degree", "countries": rows}


def build(jobs: list, majors_cfg: list, jp: dict | None, lca: dict, perm: dict) -> list:
    jp_fields = {f["ja"]: f for f in (jp or {}).get("fields", [])}
    entries = [trade_entry(j, jp_fields) for j in jobs]
    trade_socs = {j["soc"] for j in jobs}
    seen = set()
    for m in majors_cfg:
        for soc, en in m["soc"].items():
            if soc in trade_socs or soc in seen:
                continue
            seen.add(soc)
            entries.append(degree_entry(soc, m.get("soc_ko", {}).get(soc, en), en, m["slug"], lca, perm))
    order = {"yes": 0, "maybe": 1, "hard": 2}
    for e in entries:
        e["countries"].sort(key=lambda r: order[r["v"]])
    return entries
