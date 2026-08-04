#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
청약노트 사이트 자동 생성 스크립트.

한국부동산원_청약홈 분양정보 조회 서비스(odcloud)에서 APT 분양정보를 받아
'오늘' 기준 진행중/오늘마감/접수예정 공고만 골라 index.html을 재생성한다.
- 각 공고의 분양가(분양최고금액) 범위: 청약홈 주택형별 상세
- 각 공고 주변(같은 시군구) 아파트 매매 실거래 시세: 국토교통부 실거래가 상세 API

환경변수:
  SERVICE_KEY : 공공데이터포털(data.go.kr)에서 발급한 서비스 키(Decoding 키 권장)
                * 청약홈 + 국토부 실거래가 모두 활용신청(승인)되어 있어야 함(키는 계정당 1개 공용)

사용:
  python scripts/build_site.py
"""

import os
import sys
import json
import datetime
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

API_BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/"
DETAIL_OP = "getAPTLttotPblancDetail"   # 공고 단위 분양정보
MDL_OP = "getAPTLttotPblancMdl"         # 주택형별 상세(분양금액)
RTMS_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
APPLY_URL = "https://www.applyhome.co.kr/ai/aia/selectAPTLttotPblancListView.do"

UPCOMING_DAYS = 45
PER_PAGE = 1000
MAX_PAGES = 40
MARKET_MONTHS = 3      # 실거래 조회할 최근 개월 수
MARKET_MAX = 5         # 카드/모달에 보여줄 실거래 최대 건수

KST = datetime.timezone(datetime.timedelta(hours=9))

# ------------------------------------------------------------------ 법정동코드
LAWD_CD = {
    "강원|강릉시":"51150", "강원|고성군":"51820", "강원|동해시":"51170", "강원|삼척시":"51230", "강원|속초시":"51210",
    "강원|양구군":"51800", "강원|양양군":"51830", "강원|영월군":"51750", "강원|원주시":"51130", "강원|인제군":"51810",
    "강원|정선군":"51770", "강원|철원군":"51780", "강원|춘천시":"51110", "강원|태백시":"51190", "강원|평창군":"51760",
    "강원|홍천군":"51720", "강원|화천군":"51790", "강원|횡성군":"51730", "경기|가평군":"41820", "경기|고양시덕양구":"41281",
    "경기|고양시일산동구":"41285", "경기|고양시일산서구":"41287", "경기|과천시":"41290", "경기|광명시":"41210", "경기|광주시":"41610",
    "경기|구리시":"41310", "경기|군포시":"41410", "경기|김포시":"41570", "경기|남양주시":"41360", "경기|동두천시":"41250",
    "경기|부천시":"41190", "경기|부천시소사구":"41194", "경기|부천시오정구":"41196", "경기|부천시원미구":"41192", "경기|성남시분당구":"41135",
    "경기|성남시수정구":"41131", "경기|성남시중원구":"41133", "경기|수원시권선구":"41113", "경기|수원시영통구":"41117", "경기|수원시장안구":"41111",
    "경기|수원시팔달구":"41115", "경기|시흥시":"41390", "경기|안산시단원구":"41273", "경기|안산시상록구":"41271", "경기|안성시":"41550",
    "경기|안양시동안구":"41173", "경기|안양시만안구":"41171", "경기|양주시":"41630", "경기|양평군":"41830", "경기|여주시":"41670",
    "경기|연천군":"41800", "경기|오산시":"41370", "경기|용인시기흥구":"41463", "경기|용인시수지구":"41465", "경기|용인시처인구":"41461",
    "경기|의왕시":"41430", "경기|의정부시":"41150", "경기|이천시":"41500", "경기|파주시":"41480", "경기|평택시":"41220",
    "경기|포천시":"41650", "경기|하남시":"41450", "경기|화성시":"41590", "경남|거제시":"48310", "경남|거창군":"48880",
    "경남|고성군":"48820", "경남|김해시":"48250", "경남|남해군":"48840", "경남|밀양시":"48270", "경남|사천시":"48240",
    "경남|산청군":"48860", "경남|양산시":"48330", "경남|의령군":"48720", "경남|진주시":"48170", "경남|창녕군":"48740",
    "경남|창원시마산합포구":"48125", "경남|창원시마산회원구":"48127", "경남|창원시성산구":"48123", "경남|창원시의창구":"48121",
    "경남|창원시진해구":"48129", "경남|통영시":"48220", "경남|하동군":"48850", "경남|함안군":"48730", "경남|함양군":"48870",
    "경남|합천군":"48890", "경북|경산시":"47290", "경북|경주시":"47130", "경북|고령군":"47830", "경북|구미시":"47190",
    "경북|김천시":"47150", "경북|문경시":"47280", "경북|봉화군":"47920", "경북|상주시":"47250", "경북|성주군":"47840",
    "경북|안동시":"47170", "경북|영덕군":"47770", "경북|영양군":"47760", "경북|영주시":"47210", "경북|영천시":"47230",
    "경북|예천군":"47900", "경북|울릉군":"47940", "경북|울진군":"47930", "경북|의성군":"47730", "경북|청도군":"47820",
    "경북|청송군":"47750", "경북|칠곡군":"47850", "경북|포항시남구":"47111", "경북|포항시북구":"47113", "광주|광산구":"29200",
    "광주|남구":"29155", "광주|동구":"29110", "광주|북구":"29170", "광주|서구":"29140", "대구|군위군":"27720", "대구|남구":"27200",
    "대구|달서구":"27290", "대구|달성군":"27710", "대구|동구":"27140", "대구|북구":"27230", "대구|서구":"27170", "대구|수성구":"27260",
    "대구|중구":"27110", "대전|대덕구":"30230", "대전|동구":"30110", "대전|서구":"30170", "대전|유성구":"30200", "대전|중구":"30140",
    "부산|강서구":"26440", "부산|금정구":"26410", "부산|기장구":"26710", "부산|남구":"26290", "부산|동구":"26170", "부산|동래구":"26260",
    "부산|부산진구":"26230", "부산|북구":"26320", "부산|사상구":"26530", "부산|사하구":"26380", "부산|서구":"26140",
    "부산|수영구":"26500", "부산|연제구":"26470", "부산|영도구":"26200", "부산|중구":"26110", "부산|해운대구":"26350",
    "서울|강남구":"11680", "서울|강동구":"11740", "서울|강북구":"11305", "서울|강서구":"11500", "서울|관악구":"11620",
    "서울|광진구":"11215", "서울|구로구":"11530", "서울|금천구":"11545", "서울|노원구":"11350", "서울|도봉구":"11320",
    "서울|동대문구":"11230", "서울|동작구":"11590", "서울|마포구":"11440", "서울|서대문구":"11410", "서울|서초구":"11650",
    "서울|성동구":"11200", "서울|성북구":"11290", "서울|송파구":"11710", "서울|양천구":"11470", "서울|영등포구":"11560",
    "서울|용산구":"11170", "서울|은평구":"11380", "서울|종로구":"11110", "서울|중구":"11140", "서울|중랑구":"11260", "세종|":"36110",
    "울산|남구":"31140", "울산|동구":"31170", "울산|북구":"31200", "울산|울주군":"31710", "울산|중구":"31110", "인천|강화군":"28710",
    "인천|계양구":"28245", "인천|남동구":"28200", "인천|동구":"28140", "인천|미추홀구":"28177", "인천|부평구":"28237",
    "인천|서구":"28260", "인천|연수구":"28185", "인천|옹진군":"28720", "인천|중구":"28110", "전남|강진군":"46810", "전남|고흥군":"46770",
    "전남|곡성군":"46720", "전남|광양시":"46230", "전남|구례군":"46730", "전남|나주시":"46170", "전남|담양군":"46710",
    "전남|명포시":"46110", "전남|무안군":"46840", "전남|보성군":"46780", "전남|순천시":"46150", "전남|신안군":"46910",
    "전남|여수시":"46130", "전남|영광군":"46870", "전남|영암군":"46830", "전남|완도군":"46890", "전남|장성군":"46880",
    "전남|장흥군":"46800", "전남|진도군":"46900", "전남|함평군":"46860", "전남|해남군":"46820", "전남|화순군":"46790",
    "전북|고창군":"52790", "전북|군산시":"52130", "전북|김제시":"52210", "전북|남원시":"52190", "전북|무주군":"52730",
    "전북|부안군":"52800", "전북|순창군":"52770", "전북|완주군":"52710", "전북|익산시":"52140", "전북|임실군":"52750",
    "전북|장수군":"52740", "전북|전주시덕진구":"52113", "전북|전주시완산구":"52111", "전북|정읍시":"52180", "전북|진안구":"52720",
    "제주|서귀포시":"50130", "제주|제주시":"50110", "충남|계룡시":"44250", "충남|공주시":"44150", "충남|금산구":"44710",
    "충남|논산시":"44230", "충남|당진시":"44270", "충남|보령시":"44180", "충남|부여군":"44760", "충남|서산시":"44210",
    "충남|서천군":"44770", "충남|아산시":"44200", "충남|예산군":"44810", "충남|천안시동남구":"44131", "충남|천안시서북구":"44133",
    "충남|청양군":"44790", "충남|태안군":"44825", "충남|홍성군":"44800", "충북|괴산군":"43760", "충북|단양군":"43800",
    "충북|보은군":"43720", "충북|영동구":"43740", "충북|옥천군":"43730", "충북|음성군":"43770", "충북|제천시":"43150",
    "충북|증평군":"43745", "충북|진천군":"43750", "충북|청주시상당구":"43111", "충북|청주시서원구":"43112", "충북|청주시청원구":"43114",
    "충북|청주시흥덕구":"43113", "충북|충주시":"43130",
}

SIDO_NORM = {
    "서울":"서울", "서울특별시":"서울", "부산":"부산", "부산광역시":"부산", "대구":"대구", "대구광역시":"대구",
    "인천":"인천", "인천광역시":"인천", "광주":"광주", "광주광역시":"광주", "대전":"대전", "대전광역시":"대전",
    "울산":"울산", "울산광역시":"울산", "세종":"세종", "세종특별자치시":"세종", "세종시":"세종",
    "경기":"경기", "경기도":"경기", "강원":"강원", "강원도":"강원", "강원특별자치도":"강원",
    "충북":"충북", "충청북도":"충북", "충남":"충남", "충청남도":"충남",
    "전북":"전북", "전라북도":"전북", "전북특별자치도":"전북", "전남":"전남", "전라남도":"전남",
    "경북":"경북", "경상북도":"경북", "경남":"경남", "경상남도":"경남",
    "제주":"제주", "제주도":"제주", "제주특별자치도":"제주",
}
METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산"}


def resolve_lawd(addr):
    """주소 문자열 → 시군구 5자리 법정동코드. 매핑 실패 시 None(그 경우 시세 미표시)."""
    if not addr:
        return None
    toks = addr.split()
    if not toks:
        return None
    sido = SIDO_NORM.get(toks[0])
    if not sido:
        for k, v in SIDO_NORM.items():
            if toks[0].startswith(k):
                sido = v
                break
    if not sido:
        return None
    if sido == "세종":
        return LAWD_CD.get("세종|")
    gu = next((t for t in toks[1:] if t.endswith("구")), None)
    si = next((t for t in toks[1:] if t.endswith("시")), None)
    gun = next((t for t in toks[1:] if t.endswith("군")), None)
    if sido in METRO:
        key = gu or gun
        return LAWD_CD.get("{}|{}".format(sido, key)) if key else None
    if si and gu:
        return LAWD_CD.get("{}|{}{}".format(sido, si, gu))
    if si:
        return LAWD_CD.get("{}|{}".format(sido, si))
    if gun:
        return LAWD_CD.get("{}|{}".format(sido, gun))
    if gu:
        return LAWD_CD.get("{}|{}".format(sido, gu))
    return None


def extract_umd(addr):
    """주소에서 읍/면/동(법정동) 토큰 추출. 없으면 ''."""
    if not addr:
        return ""
    for t in addr.split():
        if t.endswith(("동", "읍", "면")) and not t.endswith(("구동", "시동")):
            return t
    return ""


# ------------------------------------------------------------------ 공통 유틸
def today_kst():
    return datetime.datetime.now(KST).date()


def parse_date(s):
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
    except Exception as e:  # noqa
        return "ERR", str(e)


def _params_qs(service_key, params, raw_key):
    """serviceKey 전달 방식(raw=Encoding키 그대로 / 아니면 urlencode)을 반영한 query string."""
    p = dict(params)
    if raw_key:
        rest = urllib.parse.urlencode(p)
        return "serviceKey={}{}".format(service_key, ("&" + rest if rest else ""))
    p2 = {"serviceKey": service_key}
    p2.update(p)
    return urllib.parse.urlencode(p2)


# ------------------------------------------------------------------ 청약홈(JSON)
def api_page(op, service_key, params, raw_key):
    url = API_BASE + op + "?" + _params_qs(service_key, params, raw_key)
    status, body = _request(url)
    try:
        return status, json.loads(body)
    except (ValueError, TypeError):
        return status, None


def fetch_all(service_key):
    """분양정보 전체 → (rows, raw_key). Decoding/Encoding 키 방식 자동 시도."""
    for raw_key in (False, True):
        label = "raw" if raw_key else "encoded"
        st, payload = api_page(DETAIL_OP, service_key, {"page": 1, "perPage": PER_PAGE}, raw_key)
        data = (payload or {}).get("data") or []
        if not data:
            print("[{}] 데이터 0건 (HTTP {}).".format(label, st))
            continue
        print("사용한 serviceKey 전달방식:", label)
        rows = list(data)
        if payload.get("currentCount", len(data)) >= PER_PAGE:
            for page in range(2, MAX_PAGES + 1):
                _st, p2 = api_page(DETAIL_OP, service_key, {"page": page, "perPage": PER_PAGE}, raw_key)
                d = (p2 or {}).get("data") or []
                rows.extend(d)
                if not p2 or p2.get("currentCount", len(d)) < PER_PAGE:
                    break
        return rows, raw_key
    return [], False


def fetch_price_range(service_key, raw_key, hmno, pno):
    """공고 주택형별 분양최고금액(만원) → (최저, 최고). 없으면 None."""
    if not hmno or not pno:
        return None
    params = {"page": 1, "perPage": 100,
              "cond[HOUSE_MANAGE_NO::EQ]": hmno, "cond[PBLANC_NO::EQ]": pno}
    try:
        _st, payload = api_page(MDL_OP, service_key, params, raw_key)
    except Exception:  # noqa
        return None
    amounts = []
    for d in (payload or {}).get("data") or []:
        if str(d.get("HOUSE_MANAGE_NO")) != str(hmno) or str(d.get("PBLANC_NO")) != str(pno):
            continue
        try:
            iv = int(str(d.get("LTTOT_TOP_AMOUNT")).replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        if iv > 0:
            amounts.append(iv)
    return (min(amounts), max(amounts)) if amounts else None


# ------------------------------------------------------------------ 실거래가(XML)
def _man_to_eok(man):
    return "{:.1f}억".format(man / 10000.0)


def fmt_price(rng):
    if not rng:
        return "-"
    lo, hi = rng
    return _man_to_eok(lo) if lo == hi else "{} ~ {}".format(_man_to_eok(lo), _man_to_eok(hi))


def month_strings(today, n):
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append("{:04d}{:02d}".format(y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def fetch_rtms_month(service_key, raw_key, lawd_cd, ymd):
    url = RTMS_URL + "?" + _params_qs(service_key, {"LAWD_CD": lawd_cd, "DEAL_YMD": ymd,
                                                    "pageNo": 1, "numOfRows": 1000}, raw_key)
    status, body = _request(url)
    if not body or "<" not in body:
        return [], None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return [], "PARSE"
    # 인증 오류 등
    auth = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
    if auth and "정상" not in auth:
        return [], auth
    items = []
    for item in root.iter("item"):
        d = {c.tag: (c.text or "").strip() for c in item}
        items.append(d)
    return items, None


def fetch_market(service_key, raw_key, addr, today):
    """주변(같은 시군구) 최근 아파트 매매 실거래 대표 목록과 시세 범위 반환.
    반환: (market_range_str, [trade_str,...])  실패 시 ("-", [])."""
    lawd = resolve_lawd(addr)
    if not lawd:
        return "-", []
    umd = extract_umd(addr)
    raw = []
    for ymd in month_strings(today, MARKET_MONTHS):
        items, err = fetch_rtms_month(service_key, raw_key, lawd, ymd)
        if err:
            # 인증 미승인/오류 → 조용히 시세 생략(로그만)
            print("[실거래 오류] LAWD {} {}: {}".format(lawd, ymd, err))
            return "-", []
        raw.extend(items)
    trades = []
    for d in raw:
        try:
            amt = int(str(d.get("dealAmount", "")).replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        nm = (d.get("aptNm") or "").strip()
        if not amt or not nm:
            continue
        try:
            ar = float(str(d.get("excluUseAr", "")).strip())
        except (ValueError, TypeError):
            ar = None
        y = (d.get("dealYear") or "").strip()
        m = (d.get("dealMonth") or "").strip()
        dy = (d.get("dealDay") or "0").strip()
        try:
            key = (int(y), int(m), int(dy))
        except (ValueError, TypeError):
            key = (0, 0, 0)
        trades.append({"nm": nm, "ar": ar, "amt": amt, "dong": (d.get("umdNm") or "").strip(),
                       "ym": "{}.{}".format(y[2:], m.zfill(2)) if y and m else "", "sort": key})
    if not trades:
        return "-", []
    # 같은 법정동 우선
    pool = [t for t in trades if umd and t["dong"] == umd] or trades
    # 최근순 정렬 후 아파트명 중복 제거
    pool.sort(key=lambda t: t["sort"], reverse=True)
    seen, uniq = set(), []
    for t in pool:
        if t["nm"] in seen:
            continue
        seen.add(t["nm"])
        uniq.append(t)
        if len(uniq) >= MARKET_MAX:
            break
    if not uniq:
        return "-", []
    amts = [t["amt"] for t in uniq]
    rng = fmt_price((min(amts), max(amts)))
    lst = []
    for t in sorted(uniq, key=lambda t: t["amt"], reverse=True):
        ar = "{:.0f}㎡".format(t["ar"]) if t["ar"] else ""
        parts = [t["nm"]]
        if ar:
            parts.append(ar)
        parts.append(_man_to_eok(t["amt"]))
        s = " · ".join(parts)
        if t["ym"]:
            s += " ({})".format(t["ym"])
        lst.append(s)
    return rng, lst


# ------------------------------------------------------------------ 레코드 빌드
def md(d):
    return d.strftime("%m.%d") if d else "-"


def classify(item, today):
    bgn = parse_date(item.get("RCEPT_BGNDE"))
    end = parse_date(item.get("RCEPT_ENDDE"))
    if not bgn or not end:
        return None
    if end < today:
        return None
    if today < bgn:
        if (bgn - today).days > UPCOMING_DAYS:
            return None
        return ("soon", "{} 접수시작".format(md(bgn)))
    days_left = (end - today).days
    if days_left <= 0:
        return ("today", "오늘 마감")
    if days_left == 1:
        return ("open", "내일 마감")
    return ("open", "D-{}".format(days_left))


def build_records(rows, today):
    recs = []
    for it in rows:
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
            "status": status, "dday": dday,
            "name": (it.get("HOUSE_NM") or "").strip() or "(주택명 미상)",
            "region": region, "addr": addr, "type": secd or "APT",
            "period": "{}~{}".format(md(bgn), md(end)), "announce": md(ann),
            "units": units, "price": "-", "market": "-", "trades": [],
            "link": link,
            "_addr": addr,
            "_hmno": (it.get("HOUSE_MANAGE_NO") or "").strip(),
            "_pno": (it.get("PBLANC_NO") or "").strip(),
            "_sort": (0 if status == "today" else 1 if status == "open" else 2, bgn),
        })
    recs.sort(key=lambda r: r["_sort"])
    for r in recs:
        del r["_sort"]
    return recs


def attach_prices(recs, service_key, raw_key):
    for r in recs:
        r["price"] = fmt_price(fetch_price_range(service_key, raw_key, r.get("_hmno"), r.get("_pno")))


def attach_market(recs, service_key, raw_key, today):
    for r in recs:
        try:
            rng, lst = fetch_market(service_key, raw_key, r.get("_addr"), today)
        except Exception as e:  # noqa
            print("[실거래 예외]", r.get("name"), e)
            rng, lst = "-", []
        r["market"], r["trades"] = rng, lst
    for r in recs:
        r.pop("_addr", None)
        r.pop("_hmno", None)
        r.pop("_pno", None)


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
  .kv.price .k{color:var(--blue);}
  .kv.price .v{color:var(--blue);}
  .kv.market .k{color:#2e9e5b;}
  .kv.market .v{color:#2e9e5b;}
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
  .m-kv.price .k{color:var(--blue);}
  .m-kv.price .v{color:var(--blue);}
  .m-sec{border-top:1px solid var(--line);margin-top:6px;padding-top:12px;}
  .m-sec .h{font-size:14px;font-weight:800;color:#2e9e5b;margin-bottom:8px;}
  .m-trade{display:flex;justify-content:space-between;gap:10px;font-size:13.5px;padding:5px 0;color:#4a5468;line-height:1.4;}
  .m-trade .nm{font-weight:600;}
  .m-none{font-size:13px;color:var(--gray-txt);padding:2px 0 6px;}
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
      <p>청약홈 APT분양정보(공공데이터포털) 기준 · __GEN_DATE__ 갱신 · 접수 진행/예정 공고를 자동으로 정리합니다. 카드를 누르면 분양가·주변 실거래 시세·청약홈 공고 링크를 볼 수 있어요.</p>
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
    데이터 출처: 한국부동산원 청약홈 APT분양정보 · 국토교통부 아파트 매매 실거래가(공공데이터포털) · __GEN_DATE__ 자동 갱신.<br>
    분양가는 주택형별 분양최고금액 기준, 주변 시세는 같은 시구구 최근 아파트 매매 실거래 기준입니다. 실제 청약 전 청약홈 입주자모집공고 원문에서 최종 확인하세요. © 청약노트 · 비공식 정보 정리
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
    const mkt = d.market && d.market!=="-" ? `<div class="kv market"><span class="k">주변 시세</span><span class="v">${d.market}</span></div>` : "";
    return `
    <div class="card" onclick="openModal(${idx})">
      <div class="card-top">
        <span class="pill ${PCLS[d.status]}">${LABEL[d.status]}</span>
        <span class="dday">${d.dday}</span>
      </div>
      <h3>${d.name}</h3>
      <div class="loc">${d.addr}</div>
      <div class="kv price"><span class="k">분양가</span><span class="v">${d.price}</span></div>
      ${mkt}
      <div class="kv"><span class="k">청약접수</span><span class="v">${d.period}</span></div>
      <div class="kv"><span class="k">당첨자발표</span><span class="v">${d.announce}</span></div>
      <div class="kv"><span class="k">공급 세대</span><span class="v">${d.units}세대</span></div>
      <div class="open-more">상세 보기 →</div>
    </div>`;
  }).join("");
}
function openModal(i){
  const d=DATA[i];
  const trades = (d.trades && d.trades.length)
    ? d.trades.map(t=>`<div class="m-trade"><span class="nm">${t}</span></div>`).join("")
    : `<div class="m-none">주변 실거래 데이터가 없어 표시하지 않습니다.</div>`;
  document.getElementById("modal").innerHTML=`
    <button class="close" onclick="closeModal()">×</button>
    <div class="m-status"><span class="pill ${PCLS[d.status]}">${LABEL[d.status]}</span></div>
    <h2>${d.name}</h2>
    <p class="addr">${d.addr}</p>
    <div class="tags"><span class="tag tag-type">아파트</span><span class="tag tag-supply">${d.type}</span></div>
    <div class="m-kv price"><span class="k">분양가</span><span class="v">${d.price}</span></div>
    <div class="m-kv"><span class="k">청약접수</span><span class="v">${d.period}</span></div>
    <div class="m-kv"><span class="k">당첨자발표</span><span class="v">${d.announce}</span></div>
    <div class="m-kv"><span class="k">공급 세대</span><span class="v">${d.units}세대</span></div>
    <div class="m-sec">
      <div class="h">주변 실거래 시세 (같은 시구구 · 최근)</div>
      ${trades}
    </div>
    <div class="note">분양가는 주택형별 분양최고금액 기준의 범위이고, 주변 실거래는 같은 시군구의 최근 아파트 매매 신고가입니다. 면적·동이 다를 수 있으니 참고용으로만 보시고 청약홈 원문에서 최종 확인하세요.</div>
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
    rows, raw_key = fetch_all(service_key)
    print("API 총 수신 공고:", len(rows))
    recs = build_records(rows, today)
    print("대상(진행/예정) 공고:", len(recs))
    if not recs:
        print("WARNING: 대상 공고가 0건입니다. 기존 index.html을 유지합니다.", file=sys.stderr)
        sys.exit(0)

    attach_prices(recs, service_key, raw_key)
    print("분양가 확인 공고:", sum(1 for r in recs if r.get("price") not in (None, "-")), "/", len(recs))
    attach_market(recs, service_key, raw_key, today)
    print("주변시세 확인 공고:", sum(1 for r in recs if r.get("market") not in (None, "-")), "/", len(recs))

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
