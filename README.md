# Work Route

미국·캐나다·영국·한국의 취업이민 공공데이터를 직종별·회사별로 보여주는 영문 정적 사이트입니다.
GitHub Pages로 무료 호스팅되고, 매월 5일 자동으로 최신 데이터를 받아 다시 배포됩니다.

| 섹션 | 원본 | 자동 갱신 |
|---|---|---|
| United States | 미 노동부 PERM·LCA, 국무부 비자 블루틴, 교육부 College Scorecard | 매월 |
| Canada | 고용사회개발부 LMIA 승인 고용주 목록, 이민부 Express Entry 추첨 | 매월 |
| United Kingdom | 내무부 스폰서 등록 회사 명단 | 매월 |
| South Korea | 정부 발표 수치 (`data/korea.yaml`에 직접 입력) | 수동 |

## 처음 올리기

1. GitHub에서 새 저장소를 만듭니다 (Public).
2. 이 폴더 전체를 업로드합니다.
3. **Settings → Pages → Source**를 **GitHub Actions**로 바꿉니다.
4. **Actions** 탭에서 "데이터 갱신과 배포"가 끝나면 `https://<아이디>.github.io/<저장소명>/`에서 열립니다. 첫 실행은 20분 안팎 걸립니다.
5. `config.yaml`의 `base_url`을 위 주소로 바꿔 커밋합니다.

미국 데이터 수집이 한 번이라도 성공해야 샘플 표시가 사라지고 실데이터로 바뀝니다.

## 도메인과 구글 검색 등록

1. 도메인을 사서 `config.yaml`의 `site.domain`에 입력합니다.
2. DNS에 A 레코드 4개(`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`)와 www CNAME(`<아이디>.github.io`)을 추가합니다.
3. 저장소 **Settings → Pages → Custom domain**에 도메인을 넣고 **Enforce HTTPS**를 켭니다.
4. [Google Search Console](https://search.google.com/search-console)에서 사이트를 추가하고, "HTML 태그" 인증의 content 값을 `site.google_site_verification`에 넣어 커밋합니다.
5. 인증 후 Search Console의 Sitemaps에 `sitemap.xml`을 제출합니다.

## 수익화

- `site.adsense_client`: 애드센스 승인 후 `ca-pub-...`
- `site.consult_url`: 이민 변호사·에이전시 제휴 링크. 직종 페이지마다 상담 박스가 나옵니다.

## 한국 섹션 갱신

`data/korea.yaml`의 수치와 출처 링크를 고치면 됩니다. E-9 국적별·지역별 표는 공공데이터포털
"고용노동부_외국인근로자(E9) 근무현황"을 받아 `data/korea_e9.json`으로 넣으면 표시됩니다.
형식은 `data/sample/korea_e9.json`을 참고하세요.

## 직종 추가

`config.yaml`의 `jobs`에 항목을 추가합니다. `soc`는 미국 직업코드([SOC](https://www.bls.gov/soc/)),
`noc`는 캐나다 직업코드([NOC 2021](https://noc.esdc.gc.ca/)).

## 데이터가 갱신되지 않을 때

Actions 로그에서 수집 단계를 확인하세요. 정부가 파일 양식을 바꾸면 로그에 실제 열 이름이 찍힙니다.
- 미국: `scripts/fetch_data.py`의 `pick(...)` 후보에 새 열 이름 추가
- 캐나다·영국: `scripts/fetch_world.py`
- College Scorecard 다운로드 실패: [다운로드 페이지](https://collegescorecard.ed.gov/data/)의 새 링크로 `scorecard_fos_zip` 교체

## 로컬 미리보기

```bash
pip install -r requirements.txt
python scripts/fetch_data.py && python scripts/fetch_world.py   # 생략하면 샘플로 빌드
python scripts/build_site.py
python -m http.server -d site 8000
```
