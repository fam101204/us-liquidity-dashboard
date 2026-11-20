미국 유동성 화이트 대시보드

1. 즉시 보기: index.html 더블클릭 (인터넷 연결 필요: Chart.js 차트 라이브러리)
   현재 2026-11-18까지 업로드한 초기 데이터를 표시합니다.

2. 자동 갱신 웹사이트 만들기 (무료 GitHub Pages)
   (1) GitHub에 새 Public 저장소를 생성합니다.
   (2) ZIP 파일 내용을 압축 해제해 전체 파일과 숨김 폴더 .github/workflows까지 업로드합니다.
   (3) 저장소 Settings -> Pages -> Build and deployment -> Deploy from a branch -> main -> /(root) -> Save.
   (4) Actions 탭 -> Refresh official liquidity data -> Run workflow 를 눌러 최초 수동 갱신을 테스트합니다.
   (5) 이후 워크플로가 평일 UTC 23:20 에 자동 실행되어 data/latest.json을 갱신합니다.
   (6) Pages 주소: https://[계정명].github.io/[저장소명]/

3. 자동갱신 주의사항
   - FRED 사이트가 연결 실패할 경우 갱신은 실패하며 지난 성공 데이터가 유지됩니다.
   - Actions에서 실행 성공 여부 확인, 웹사이트 상단 실제 관측기준일 확인.
   - GitHub Pages의 자동 갱신을 이용하려면 저장소 Actions 쓰기 권한이 필요할 수 있습니다.
     Settings -> Actions -> General -> Workflow permissions -> Read and write permissions.
   - GitHub Actions cron 실행은 지연/누락될 수 있으며, CSV 내 Fed와 지급준비금은 주간 자료입니다.
   - 미국 시장 휴일 / 발표 지연이 있어 모든 자료가 같은 날짜에 갱신되지는 않습니다.
   - 인터넷 연결이 있어야 CDN Chart.js 차트를 표시할 수 있습니다.

4. 고지
   간이 순유동성 = Fed 총자산 - TGA - ON RRP.
   투자 조언·미래수익 예측이 아닙니다.

5. V3 종합점수/누적 기록
   - 0~100점, 높을수록 금융시장 환경이 우호적이라는 시험 모델입니다.
   - 처음 20거래일은 점수 산출 불가, 다음 거래일부터 매일 누적됩니다.
   - GitHub Actions가 성공할 때 data/observation_history.json 과 data/score_history.json 에 모든 과거 거래일을 누적 보존합니다.
   - 고정 가중치/범위의 검증되지 않은 관찰용 점수로 투자신호가 아닙니다.
   - GitHub 업로드 시 기존 저장소에서 index.html, initial-data.js, update_data.py, score_model.py, data 폴더, .github 폴더를 모두 교체해 주세요.

6. V4 점수 구간별 이후 나스닥 수익률
 - 0~29 / 30~49 / 50~69 / 70~100점 그룹별 5·20거래일 이후 평균 수익률 및 승률을 표시합니다.
 - 미래 기간이 아직 끝나지 않은 날은 계산에서 제외합니다.
 - 데이터가 자동 갱신될 때 data/forward_analysis.json 또한 누적 재계산됩니다.
 - 중첩 관측치, 짧은 분석기간, 임의 점수 모델 등으로 예측력을 확정할 수 없습니다.
