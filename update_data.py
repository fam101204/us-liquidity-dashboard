#!/usr/bin/env python3
"""Refresh with official FRED and Treasury sources; never overwrite on partial failure."""
import io, json, os, sys, time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import pandas as pd
import requests
from score_model import score_from_rows
from forward_test import build_forward_analysis

ROOT=Path(__file__).resolve().parent
DIR=ROOT/'data'; DIR.mkdir(exist_ok=True)
START=os.environ.get('START_DATE','2019-11-01')  # warmup before 2020 for 20-day scoring
FRED=['WALCL','RRPONTSYD','NASDAQCOM','WRESBAL','DGS10','BAMLH0A0HYM2']
S=requests.Session();S.headers.update({'User-Agent':'Mozilla/5.0 research-dashboard','Accept':'text/csv,application/json,*/*'})

def download(url,params=None,secs=30):
    error=None
    for i in range(3):
        try:
            r=S.get(url,params=params,timeout=(12,secs))
            r.raise_for_status(); return r
        except requests.RequestException as e:
            error=e;print('Retry',i+1, url, type(e).__name__,flush=True);time.sleep(1+i*2)
    raise RuntimeError(f'공식 데이터 조회 실패: {url}: {error}')

def _validate_fred_series(code, out, source):
    """Reject invalid or stale alternative data rather than silently changing the chart."""
    out=out.sort_index()
    out=out[~out.index.duplicated(keep='last')]
    out=out[out.index>=pd.Timestamp(START)]
    if out.empty or len(out)<100:
        raise ValueError(f'{code} {source}: insufficient observations ({len(out)})')
    age=(pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()-out.index.max()).days
    # WALCL and WRESBAL are weekly; a longer bound permits holiday/reporting lag.
    maximum_age=17 if code in ('WALCL','WRESBAL') else 10
    if age<0 or age>maximum_age:
        raise ValueError(f'{code} {source}: stale data, latest={out.index.max().date()}, age={age} days')
    return out


def fred(code):
    """Official FRED API v1, with a GitHub Actions secret (no scraped CSV/mirrors)."""
    key=os.environ.get('FRED_API_KEY','').strip()
    if not key:
        raise RuntimeError('FRED_API_KEY 미설정: GitHub Settings > Secrets and variables > Actions 에 등록하세요.')
    if not (len(key)==32 and key.isalnum()):
        raise RuntimeError('FRED_API_KEY 형식 오류: 32자 영문/숫자 키를 다시 확인하세요.')
    url='https://api.stlouisfed.org/fred/series/observations'
    params={'series_id':code, 'api_key':key, 'file_type':'json',
            'observation_start':START, 'sort_order':'asc'}
    error=None
    for attempt in range(1,4):
        try:
            r=S.get(url,params=params,timeout=(15,35))
            if r.status_code!=200:
                # Don't print the response URL or untrusted bodies, to avoid leaking the API key.
                raise RuntimeError(f'HTTP {r.status_code} (인증 오류 400/401이면 API 키를 확인하세요)')
            body=r.json()
            obs=body.get('observations')
            if not isinstance(obs,list) or not obs:
                raise ValueError('observations 배열 없음: FRED 응답 형식 확인 필요')
            frame=pd.DataFrame(obs)
            if not {'date','value'}.issubset(frame.columns):
                raise ValueError('date/value 컬럼 없음')
            frame['date']=pd.to_datetime(frame['date'],errors='coerce')
            frame['value']=pd.to_numeric(frame['value'],errors='coerce')
            series=frame.dropna(subset=['date','value']).set_index('date')['value']
            series.name=code
            output=_validate_fred_series(code,series,'FRED API v1')
            print(f'[FRED {code}] 성공 | 관측치 {len(output)}개 | 최신 {output.index.max().date()}',flush=True)
            return output
        except (requests.RequestException,RuntimeError,ValueError,KeyError,TypeError) as e:
            error=e
            # Never show request URLs; they may contain the API credential.
            detail = str(e) if isinstance(e,(RuntimeError,ValueError)) else '연결/응답 오류'
            print(f'[FRED {code}] {attempt}/3 실패: {type(e).__name__}: {detail[:140]}',flush=True)
            if isinstance(e,RuntimeError) and 'HTTP 4' in str(e):
                break  # retrying invalid key has no benefit
            if attempt<3: time.sleep(attempt*2)
    raise RuntimeError(f'FRED 공식 API {code} 조회 실패: {type(error).__name__}. '
                       f'공식 API 연결 및 GitHub Secret 설정을 확인하세요.')


def check_sources():
    """Connectivity check, without touching saved data."""
    print('공식 데이터 연결 검사: 저장 데이터는 변경하지 않습니다.',flush=True)
    key=os.environ.get('FRED_API_KEY','').strip()
    if not(key and len(key)==32 and key.isalnum()):
        raise RuntimeError('FRED_API_KEY 누락 또는 형식 오류. GitHub Actions Secrets를 먼저 설정하세요.')
    url='https://api.stlouisfed.org/fred/series/observations'
    try:
        r=S.get(url,params={'api_key':key,'series_id':'WALCL','file_type':'json',
                            'observation_start':(date.today()-timedelta(days=40)).isoformat()},
                timeout=(15,35))
    except requests.RequestException:
        raise RuntimeError('FRED API 연결 실패: api.stlouisfed.org 접속 여부를 확인하세요.') from None
    if r.status_code!=200:
        raise RuntimeError(f'FRED API HTTP {r.status_code}: 다른 주소로 임의 전환하지 않습니다.')
    body=r.json()
    if not body.get('observations'):
        raise RuntimeError('FRED API가 반환한 관측치가 없습니다.')
    print('FRED API 인증 및 관측치 조회 성공',flush=True)
    try:
        r=S.get('https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance',
                params={'page[size]':'1','sort':'-record_date'},timeout=(15,35))
    except requests.RequestException:
        raise RuntimeError('미국 재무부 FiscalData API 연결 실패') from None
    if r.status_code!=200 or not r.json().get('data'):
        raise RuntimeError(f'미국 재무부 API 조회 실패: HTTP {r.status_code}')
    print('미국 재무부 API 접속 성공',flush=True)

def treasury():
    """Load every DTS API page, including pre-2021 Federal Reserve Account naming.
    Important: close_today_bal is empty for post-April 2022 TGA closing rows;
    the Treasury stores closing balance in open_today_bal for those rows.
    DTS values are millions of dollars.
    """
    endpoint='https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance'
    params={'filter':f'record_date:gte:{START}',
            'fields':'record_date,account_type,open_today_bal,close_today_bal',
            'page[size]':'5000','sort':'record_date'}
    allrows=[]; page=1; total_pages=1
    while page<=total_pages:
        print(f'Treasury page {page}/{total_pages}',flush=True)
        params['page[number]']=str(page)
        body=download(endpoint,params,secs=70).json()
        meta=body.get('meta',{})
        total_pages=int(meta.get('total-pages',1))
        if total_pages>100: raise ValueError('Unexpected Treasury page count')
        part=body.get('data',[])
        if not isinstance(part,list) or not part: raise ValueError(f'Empty Treasury page {page}')
        allrows.extend(part);page+=1
    d=pd.DataFrame(allrows)
    required={'record_date','account_type','open_today_bal','close_today_bal'}
    if not required.issubset(d):raise ValueError('Treasury fields missing')
    ac=d['account_type'].astype(str).str.lower()
    # Pre-Oct 2021 Federal Reserve Account; newer Treasury General Account.
    mask=ac.str.contains(r'(treasury general account|federal reserve account|\btga\b)',regex=True) & ac.str.contains('closing balance')
    d=d.loc[mask].copy()
    d['record_date']=pd.to_datetime(d['record_date'],errors='coerce')
    # DTS changed the closing-balance storage field in April 2022.
    # For a closing-balance row, use close_today_bal when present; else open_today_bal.
    close=pd.to_numeric(d['close_today_bal'],errors='coerce')
    open_=pd.to_numeric(d['open_today_bal'],errors='coerce')
    d['TGA']=close.combine_first(open_)
    d=d.dropna(subset=['record_date','TGA'])
    if d.empty: raise ValueError('No TGA closing-balance records: inspect account_type names')
    if d['record_date'].duplicated().any():
        dup=d.loc[d['record_date'].duplicated(),['record_date','account_type']]
        raise ValueError(f'Duplicate TGA dates: {dup.head().to_dict("records")}')
    t=d.set_index('record_date')['TGA'].sort_index()
    if (pd.Timestamp.today().normalize()-t.index.max()).days>10:raise ValueError('Treasury TGA stale')
    return t

def asof(series,dates,lag=0,div=1):
    s=series.copy();s.index=s.index+pd.Timedelta(days=lag)
    return s.reindex(s.index.union(dates)).sort_index().ffill().reindex(dates)/div

def main():
    print('Fetching FRED official data',flush=True)
    f={k:fred(k) for k in FRED}
    print('Fetching US Treasury TGA',flush=True)
    t=treasury()
    dates=f['NASDAQCOM'].index[f['NASDAQCOM'].index>=pd.Timestamp('2020-01-01')]
    if len(dates)<1200:raise ValueError('Historical Nasdaq observations insufficient; expected 2020 onward')
    d=pd.DataFrame(index=dates)
    d['NASDAQCOM']=f['NASDAQCOM'].reindex(dates)
    d['Fed_USD_trillion']=asof(f['WALCL'],dates,lag=2,div=1e6)
    d['TGA_USD_trillion']=asof(t,dates,div=1e6)
    d['RRP_USD_trillion']=asof(f['RRPONTSYD'],dates,div=1e3)
    d['Bank_Reserves_USD_trillion']=asof(f['WRESBAL'],dates,lag=2,div=1e6)
    d['UST10Y_pct']=asof(f['DGS10'],dates)
    d['HY_OAS_pct']=asof(f['BAMLH0A0HYM2'],dates)
    # HY OAS is only distributed by FRED for the latest ~3 years (since Apr 2026).
    # Keep earlier HY observations and scores missing; NEVER backfill synthetic prices.
    mandatory=[k for k in d.columns if k!='HY_OAS_pct']
    if d[mandatory].isna().any().any():
        raise ValueError('핵심 시계열에 결측값: 초기 정렬 또는 원자료 확인 필요')
    d['Net_Liquidity_USD_trillion']=d['Fed_USD_trillion']-d['TGA_USD_trillion']-d['RRP_USD_trillion']
    d['Net_Liquidity_Index_100']=100*d['Net_Liquidity_USD_trillion']/d['Net_Liquidity_USD_trillion'].iloc[0]
    d['NASDAQ_Index_100']=100*d['NASDAQCOM']/d['NASDAQCOM'].iloc[0]
    d.index.name='Date';d=d.reset_index();d['Date']=d['Date'].dt.strftime('%Y-%m-%d')
    # atomic writes only after all upstream sources pass validation
    meta={'last_refresh_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'start_date':d.iloc[0]['Date'], 'end_date':d.iloc[-1]['Date'],'asof': {k:str(v.index[-1].date()) for k,v in f.items()}|{'TGA':str(t.index[-1].date())},'source':'Official FRED API v1 + official U.S. Treasury FiscalData API'}
    # to_json converts pre-2023 HY missing values to valid JSON null (not NaN).
    recent=json.loads(d.to_json(orient='records',double_precision=9))
    # Preserve and append all observations since 2020; recalculate scores and tests on entire history.
    # Scores must use preceding 20 sessions, never future observations.
    hist_file=DIR/'observation_history.json'
    old=[]
    if hist_file.exists():
        old=json.loads(hist_file.read_text(encoding='utf-8')).get('rows',[])
    elif (DIR/'latest.json').exists():
        old=json.loads((DIR/'latest.json').read_text(encoding='utf-8')).get('rows',[])
    merged={r['Date']:r for r in old if isinstance(r,dict) and 'Date' in r}
    for r in recent: merged[r['Date']]=r
    full=[merged[k] for k in sorted(merged)]
    scores=score_from_rows(full)
    forward=build_forward_analysis(full,scores)
    meta['score_version']='v1'
    meta['score_available_start']=next((r['Date'] for r in scores if r.get('score') is not None), None)
    meta['limitation']='HY OAS available only ~3 years from FRED after Apr 2026. Earlier score dates intentionally null.'
    payload={'meta':meta,'rows':recent,'score_history':scores,'forward_analysis':forward}
    meta['history_rows']=len(full)
    meta['historical_backfill_start']=full[0]['Date']
    meta['validation_policy']='Descriptive 2020–2024 vs 2025+ split; overlapping forward windows, NOT a proven strategy'
    payload['meta']=meta
    # Write outputs only once all input validation and scoring succeed.
    for name,obj in [('observation_history.json',{'rows':full}),('score_history.json',{'meta':{'score_version':'v1'},'rows':scores}),('forward_analysis.json',forward),('latest.json',payload)]:
        target=DIR/name;tmp=DIR/(name+'.tmp')
        tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        os.replace(tmp,target)
    print('Updated',meta['end_date'])

if __name__=='__main__':
    try:
        if '--check' in sys.argv: check_sources()
            # V7 update test
        else: main()
    except Exception as e:print('UPDATE FAILED; existing snapshot preserved:',e,file=sys.stderr);sys.exit(1)
