미국 유동성 V5 - 2020년 이후 과거 데이터 수집 및 기간별 성과 검증

1) zip 파일 압축 해제 후 GitHub 저장소의 기존 파일을 교체합니다.
2) Actions > Refresh official liquidity data > Run workflow를 실행합니다.
3) 성공 시 data/latest.json 및 2020년 이후 score_history가 갱신됩니다.
4) Settings > Pages > main 브랜치 / root에서 웹페이지를 게시합니다.

로컬 실행: py -m pip install -r requirements.txt 후 py update_data.py
기존 FRED 연결 제한이 있으면 GitHub Actions 환경에서 실행하는 방법을 권장합니다.
정상 검증 전에는 2026년 초기 150거래일 자료가 표시됩니다.
자료 출처: FRED(WALCL,RRPONTSYD,NASDAQCOM,WRESBAL,DGS10,BAMLH0A0HYM2) 및 미국 재무부 DTS.
주의: 2020년부터의 전체 데이터는 첫 온라인 실행에 성공해야 생성됩니다.
점수는 휴리스틱으로서 학습된 모델이 아니며 구간별 결과는 기술 통계입니다.
