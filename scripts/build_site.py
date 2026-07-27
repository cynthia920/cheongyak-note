#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
청약노트 사이트 자동 생성 스크립트.

한국부동산원_청약홈 분양정보 조회 서비스(odcloud)에서 APT 분양정보를 받아
'오늘' 기준 진행중/오늘마감/접수예정 공고만 골라 index.html을 재생성한다.

환경변수:
  SERVICE_KEY : 공공데이터포털(data.go.kr)에서 발급한 서비스 키(Decoding 키 권장)

사용:
  python scripts/build_site.py
"""

import os
import sys
import json
import html
import datetime
import urllib.parse
import urllib.request
import urllib.error

API_URL = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
APPLY_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do"

# '오늘' 이후 며칠까지의 '접수예정' 공고를 포함할지
UPCOMING_DAYS = 45
PER_PAGE = 1000
MAX_PAGES = 40

KST = datetime.timezone(datetime.timedelta(hours=9))


def today_kst():
    return datetime.datetime.now(KST).date()


def parse_date(s):
    """'YYYY-MM-DD' 또는 'YYYYMMDD' 문자열을 date로 파싱. 실패 시 None."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cheongyak-note/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        return e.code, body


def _url_encoded(service_key, page):
    return API_URL + "?" + urllib.parse.urlencode(
        {"serviceKey": service_key, "page": page, "perPage": PER_PAGE}
    )


def _url_raw(service_key, page):
    # 이미 URL 인코딩된 키(Encoding 키)를 그대로 붙이는 방식
    return "{}?serviceKey={}&page={}&perPage={}".format(API_URL, service_key, page, PER_PAGE)


def fetch_all(service_key):
    """API를 페이지 단위로 ꪨ두 받아 data 배열을 합쳐 반환.
    Decoding 키(urlencode)와 Encoding 키(raw) 두 방식을 자동 시도한다."""
    for label, build in (("encoded", _url_encoded), ("raw", _url_raw)):
        status, body = _request(build(service_key, 1))
        try:
            payload = json.loads(body)
        except ValueError:
            print("[{}] JSON 파싱 실패 (HTTP {}): {}".format(label, status, body[:250]))
            continue
        data = payload.get("data") or []
        if not data:
            print("[{}] 데이터 0건 (HTTP {}). 응답요약: {}".format(label, status, body[:250]))
            continue
        # 성공한 방식으로 전체 페이지 수집
        print("사용한 serviceKey 전달방식:", label)
        rows = list(data)
        if payload.get("currentCount", len(data)) >= PER_PAGE:
            for page in range(2, MAX_PAGES + 1):
                _s, b = _request(build(service_key, page))
                try:
                    p = json.loads(b)
                except ValueError:
                    break
                d = p.get("data") or []
                rows.extend(d)
                if p.get("currentCount", len(d)) < PER_PAGE:
                    break
        return rows
    return []


def md(d):
    """date -> 'MM.DD'"""
    return d.strftime("%m.%d") if d else "-"


def classify(item, today):
    """공고를 상태(open/today/soon)와 D-day 문구로 분류. 대상 아니면 None."""
    bgn = parse_date(item.get("RCEPT_BGNDE"))
    end = parse_date(item.get("RCEPT_ENDDE"))
    if not bgn or not end:
        return None
    if end < today:
        return None  # 이미 마감
    if today < bgn:
        # 접수예정
        if (bgn - today).days > UPCOMING_DAYS:
            return None
        return ("soon", "{} 접수시작".format(md(bgn)))
    # 접수 진행 중(오늘이 접수 기간 안)
    days_left = (end - today).days
    if days_left <= 0:
        return ("today", "오늘 마감")
    if days_left == 1:
        return ("open", "내일 마감")
    return ("open", "D-{}".format(days_left))


def build_records(rows, today):
    recs = []
    for it in rows:
        # APT만 (혹시 다른 유형이 섞여 오면 제외)
        secd = (it.get("HOUSE_SECD_NM") or "").strip()
        result = classify(it, today)
        if not result:
            continue
        status, dday = result
        bgn = parse_date(it.get("RCEPT_BGNDE"))
        end = parse_date(it.get("RCEPT_ENDDE"))
        ann = parse_date(it.get("PRZWNER_PRESNATN_DE"))
        region = (it.get("SUBSCRPT_AREA_CODE_NM") or "").strip() or "기타"
        addr = (it.get("HSSPLY_ADRES") or "").strip() or region
        units = it.get("TOT_SUPLY_HSHLDCO")
        try:
            units = "{:,}".format(int(str(units).replace(",", ""))) if units not in (None, "") else "-"
        except (ValueError, TypeError):
            units = str(units) if units else "-"
        link = (it.get("HMPG_ADRES") or "").strip() or APPLY_URL
        if not link.startswith("http"):
            link = APPLY_URL
        recs.append({
            "status": status,
            "dday": dday,
            "name": (it.get("HOUSE_NM") or "").strip() or "(주택명 미상)",
            "region": region,
            "addr": addr,
            "type": secd or "APT",
            "period": "{}~{}".format(md(bgn), md(end)),
            "announce": md(ann),
            "units": units,
            "link": link,
            "_sort": (0 if status == "today" else 1 if status == "open" else 2, bgn),
        })
    # 오늘마감 > 접수중 > 접수예정, 그 안에서는 접수시작일 순
    recs.sort(key=lambda r: r["_sort"])
    for r in recs:
        del r["_sort"]
    return recs


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>청약노트 · 아파트 청약 정보</title>
<style>
  :root{
    --navy:#1f2a52; --blue:#3b5bd9; --blue-soft:#eaefff;
    --gray-txt:#8a93a6; --line:#eef0f4; --box:#f4f6fa; --bg:#eef1f6;
    --green-bg:#e4f5ea; --green:#2e9e5b;
    --red-bg:#fdeaea; --red:#d94b4b;
    --orange-bg:#fef1e0; --orange:#e08a2b;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  html{scroll-behavior:smooth;}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","맑은 고딕",system-ui,sans-serif;
    background:var(--bg);color:var(--navy);-webkit-font-smoothing:antialiased;padding-bottom:60px;
  }
  header{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);}
  .head-inner{max-width:1080px;margin:0 auto;padding:16px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
  .brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;letter-spacing:-.5px;}
  .brand .dot{width:12px;height:12px;border-radius:4px;background:var(--blue);}
  .search{flex:1;min-width:180px;position:relative;}
  .search input{width:100%;border:1.5px solid #e2e6ef;border-radius:12px;padding:11px 14px 11px 40px;font-size:15px;background:#fff;color:var(--navy);outline:none;}
  .search input:focus{border-color:var(--blue);}
  .search svg{position:absolute;left:13px;top:50%;transform:translateY(-50%);opacity:.4;}
  .wrap{max-width:1080px;margin:0 auto;padding:0 20px;}
  .hero{padding:26px 0 10px;}
  .hero h1{font-size:26px;font-weight:800;letter-spacing:-.6px;}
  .hero p{color:#6b7488;font-size:14.5px;margin-top:8px;line-height:1.6;}
  .filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0 6px;}
  .chip{border:1.5px solid #e2e6ef;background:#fff;color:#5b6478;font-weight:700;font-size:14px;padding:8px 16px;border-radius:999px;cursor:pointer;transition:.15s;}
  .chip:hover{border-color:#c9d0de;}
  .chip.active{background:var(--navy);border-color:var(--navy);color:#fff;}
  select.region{border:1.5px solid #e2e6ef;background:#fff;color:#5b6478;font-weight:700;font-size:14px;padding:8px 14px;border-radius:999px;cursor:pointer;outline:none;margin-left:auto;}
  .count{color:var(--gray-txt);font-size:14px;margin:14px 0 4px;font-weight:600;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;padding:8px 0 20px;}
  .card{background:#fff;border-radius:18px;border-left:6px solid var(--blue);box-shadow:0 6px 20px rgba(31,42,82,.07);padding:20px 20px 18px;cursor:pointer;transition:transform .12s, box-shadow .12s;display:flex;flex-direction:column;}
  .card:hover{transform:translateY(-3px);box-shadow:0 12px 28px rgba(31,42,82,.13);}
  .card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;}
  .pill{font-weight:700;font-size:13px;padding:6px 13px;border-radius:999px;}
  .pill-open{background:var(--green-bg);color:var(--green);}
  .pill-today{background:var(--red-bg);color:var(--red);}
  .pill-soon{background:var(--orange-bg);color:var(--orange);}
  .dday{font-size:13px;font-weight:700;color:var(--gray-txt);}
  .card h3{font-size:18.5px;font-weight:800;letter-spacing:-.4px;line-height:1.32;margin-bottom:8px;}
  .card .loc{color:#6b7488;font-size:13.5px;margin-bottom:14px;}
  .kv{display:flex;justify-content:space-between;font-size:14px;padding:5px 0;border-top:1px solid var(--line);}
  .kv .k{color:var(--gray-txt);}
  .kv .v{font-weight:700;}
  .card .open-more{margin-top:14px;color:var(--blue);font-weight:700;font-size:14px;text-align:right;}
  .empty{text-align:center;color:var(--gray-txt);padding:60px 0;font-size:15px;}
  .overlay{position:fixed;inset:0;background:rgba(31,42,82,.45);z-index:100;display:none;align-items:flex-start;justify-content:center;padding:24px 16px;overflow-y:auto;}
  .overlay.on{display:flex;}
  .modal{background:#fff;border-radius:22px;max-width:440px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.25);padding:26px 24px 12px;position:relative;animation:pop .18s ease;}
  @keyframes pop{from{transform:scale(.96);opacity:0;}to{transform:scale(1);opacity:1;}}
  .close{position:absolute;top:16px;right:16px;width:34px;height:34px;border:none;border-radius:10px;background:var(--box);color:#5b6478;font-size:20px;cursor:pointer;line-height:1;}
  .close:hover{background:#e8ebf2;}
  .m-status{margin-bottom:16px;}
  .modal h2{font-size:24px;font-weight:800;letter-spacing:-.5px;margin-bottom:10px;padding-right:30px;}
  .modal .addr{color:#6b7488;font-size:15px;margin-bottom:14px;}
  .tags{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;}
  .tag{font-size:13.5px;font-weight:600;padding:6px 14px;border-radius:10px;}
  .tag-type{background:#f1f3f7;color:#5b6478;}
  .tag-supply{background:var(--blue-soft);color:var(--blue);}
  .m-kv{display:flex;justify-content:space-between;font-size:15px;padding:11px 0;border-top:1px solid var(--line);}
  .m-kv .k{color:var(--gray-txt);}
  .m-kv .v{font-weight:700;}
  .note{background:#fbfbe9;color:#8a7a2b;font-size:12.5px;line-height:1.5;border-radius:10px;padding:10px 13px;margin-top:14px;}
  .m-footer{border-top:1px solid var(--line);margin-top:14px;padding:16px 0 12px;text-align:right;}
  .m-link{color:var(--blue);font-weight:700;font-size:15px;text-decoration:none;}
  footer{max-width:1080px;margin:0 auto;padding:24px 20px;color:var(--gray-txt);font-size:12.5px;line-height:1.6;text-align:center;}
  @media(max-width:520px){.hero h1{font-size:22px;}.modal{border-radius:20px 20px 0 0;align-self:flex-end;}}
</style>
</head>
<body>
  <header>
    <div class="head-inner">
      <div class="brand"><span class="dot"></span>청약노트</div>
      <div class="search">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        <input id="q" type="text" placeholder="단지명 · 지역 검색">
      </div>
    </div>
  </header>

  <div class="wrap">
    <div class="hero">
      <h1>아파트 청약 정보</h1>
      <p>청약홈 APT분양정보(공공데이터포털) 기준 · __GEN_DATE__ 갱신 · 접수 진행/예정 공고를 자동으로 정리합니다. 카드를 누르면 일정과 청약홈 공고 링크를 볼 수 있어요.</p>
    </div>

    <div class="filters" id="statusFilters">
      <button class="chip active" data-s="all">전체</button>
      <button class="chip" data-s="open">접수중</button>
      <button class="chip" data-s="today">오늘 마감</button>
      <button class="chip" data-s="soon">접수예정</button>
      <select class="region" id="regionSel"><option value="all">전체 지역</option></select>
    </div>
    <div class="count" id="count"></div>
    <div class="grid" id="grid"></div>
    <div class="empty" id="empty" style="display:none;">해당 조건의 공고가 없습니다.</div>
  </div>

  <footer>
    데이터 출처: 한국부동산원 청약홈 APT분양정보(공공데이터포털) · __GEN_DATE__ 자동 갱신.<br>
    실제 청약 전 청약홈 입주자모집공고 원문에서 최종 확인하세요. © 청약노트 · 비공식 정보 정리
  </footer>

  <div class="overlay" id="overlay"><div class="modal" id="modal"></div></div>

<script>
const DATA=__DATA__;
const LABEL={open:"접수중",today:"오늘 마감",soon:"접수예정"};
const PCLS={open:"pill-open",today:"pill-today",soon:"pill-soon"};

let curStatus="all", curRegion="all", curQ="";

const regions=[...new Set(DATA.map(d=>d.region))];
const regionSel=document.getElementById("regionSel");
regions.forEach(r=>{const o=document.createElement("option");o.value=r;o.textContent=r;regionSel.appendChild(o);});

function filtered(){
  return DATA.filter(d=>
    (curStatus==="all"||d.status===curStatus) &&
    (curRegion==="all"||d.region===curRegion) &&
    (curQ===""||(d.name+d.region+d.addr).toLowerCase().includes(curQ))
  );
}
function render(){
  const list=filtered();
  document.getElementById("count").textContent=`총 ${list.length}건`;
  const grid=document.getElementById("grid");
  document.getElementById("empty").style.display=list.length?"none":"block";
  grid.innerHTML=list.map((d)=>{
    const idx=DATA.indexOf(d);
    return `
    <div class="card" onclick="openModal(${idx})">
      <div class="card-top">
        <span class="pill ${PCLS[d.status]}">${LABEL[d.status]}</span>
        <span class="dday">${d.dday}</span>
      </div>
      <h3>${d.name}</h3>
      <div class="loc">${d.addr}</div>
      <div class="kv"><span class="k">청약접수</span><span class="v">${d.period}</span></div>
      <div class="kv"><span class="k">당첨자발표</span><span class="v">${d.announce}</span></div>
      <div class="kv"><span class="k">공급 세대</span><span class="v">${d.units}세대</span></div>
      <div class="open-more">상세 보기 →</div>
    </div>`;
  }).join("");
}
function openModal(i){
  const d=DATA[i];
  document.getElementById("modal").innerHTML=`
    <button class="close" onclick="closeModal()">×</button>
    <div class="m-status"><span class="pill ${PCLS[d.status]}">${LABEL[d.status]}</span></div>
    <h2>${d.name}</h2>
    <p class="addr">${d.addr}</p>
    <div class="tags"><span class="tag tag-type">아파트</span><span class="tag tag-supply">${d.type}</span></div>
    <div class="m-kv"><span class="k">청약접수</span><span class="v">${d.period}</span></div>
    <div class="m-kv"><span class="k">당첨자발표</span><span class="v">${d.announce}</span></div>
    <div class="m-kv"><span class="k">공급 세대</span><span class="v">${d.units}세대</span></div>
    <div class="note">주탙형별 공급금액·세대수 등 상세 내용은 청약홈 입주자모집공고 원문에서 확인하세요.</div>
    <div class="m-footer"><a class="m-link" href="${d.link}" target="_blank" rel="noopener">청약홈에서 확인 →</a></div>`;
  document.getElementById("overlay").classList.add("on");
  document.body.style.overflow="hidden";
}
function closeModal(){document.getElementById("overlay").classList.remove("on");document.body.style.overflow="";}
document.getElementById("overlay").addEventListener("click",e=>{if(e.target.id==="overlay")closeModal();});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});
document.getElementById("statusFilters").addEventListener("click",e=>{
  if(!e.target.classList.contains("chip"))return;
  document.querySelectorAll(".chip").forEach(c=>c.classList.remove("active"));
  e.target.classList.add("active");curStatus=e.target.dataset.s;render();
});
regionSel.addEventListener("change",e=>{curRegion=e.target.value;render();});
document.getElementById("q").addEventListener("input",e=>{curQ=e.target.value.trim().toLowerCase();render();});
render();
</script>
</body>
</html>
"""


def main():
    service_key = os.environ.get("SERVICE_KEY", "").strip()
    if not service_key:
        print("ERROR: 환경변수 SERVICE_KEY 가 없습니다.", file=sys.stderr)
        sys.exit(1)

    today = today_kst()
    print("오늘(KST):", today)
    rows = fetch_all(service_key)
    print("API 총 수신 공고:", len(rows))
    recs = build_records(rows, today)
    print("대상(진행/예정) 공고:", len(recs))
    if not recs:
        print("WARNING: 대상 공고가 0건입니다. 기존 index.html을 유지합니다.", file=sys.stderr)
        sys.exit(0)

    gen_date = today.strftime("%Y.%m.%d")
    out = TEMPLATE.replace("__DATA__", json.dumps(recs, ensure_ascii=False))
    out = out.replace("__GEN_DATE__", gen_date)

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print("index.html 생성 완료:", path)


if __name__ == "__main__":
    main()
