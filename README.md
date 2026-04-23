# 주식 관리 대시보드

처음엔 비어 있는 상태에서 시작하고, 사용자가 직접 종목과 수익실현을 입력해 채워가는 Streamlit 대시보드입니다.

## 실행

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

## 현재 동작

- `data/portfolio_data.json`을 기준으로 미국주식 / 국내주식 대시보드를 표시
- 종목명 뒤에 `+`를 붙여 입력하면 수익실현 표시 상태 저장
- 새 종목 추가 가능
- 입력 후 JSON 파일에 저장
- 처음 실행하면 모든 값이 0인 상태에서 시작

## 데이터 파일

기본 데이터는 `data/portfolio_data.json`에 들어 있으며, 빈 상태 템플릿으로 시작합니다.
