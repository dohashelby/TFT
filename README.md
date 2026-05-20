# TFT Advisor

TFT 실시간 AI 추천 도구. Claude Vision API로 화면을 분석하고, 지금 당장 뭘 해야 하는지 화면 오버레이로 알려줍니다.

## 추천 항목
- **BUY**: 지금 사야 할 챔피언
- **SELL**: 팔아야 할 챔피언
- **ITEM**: 아이템 조합 방법
- **AUGMENT**: 증강체 선택
- **ECONOMY**: 골드 관리 / 롤 타이밍
- **URGENT**: 즉시 행동 필요 (체력 위험 등)

## 설치

1. `setup.bat` 더블클릭
2. `config.json` 에 API 키 입력
   - API 키 발급: https://console.anthropic.com/
3. TFT를 **창모드(보더리스)** 로 실행
   - TFT 설정 > 비디오 > 창모드(보더리스)
4. `python main.py` 실행

## 오버레이 위치 조정

`config.json` 에서 `overlay` 섹션 수정:
```json
"overlay": {
  "x": 1480,   ← 가로 위치 (오른쪽으로 갈수록 증가)
  "y": 20,     ← 세로 위치
  "width": 420,
  "height": 680,
  "alpha": 0.88
}
```

## 메타 데이터 업데이트

`src/meta/comps.json` 을 수정해서 현재 시즌 덱 추가 가능.
MetaTFT(metatft.com) 참고.
