@echo off
echo ====================================
echo  TFT Advisor - 설치 시작
echo ====================================
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo 챔피언/아이템 이미지 다운로드 중...
python setup_assets.py

echo.
echo ====================================
echo  설치 완료!
echo.
echo  실행 방법:
echo  1. TFT를 창모드(보더리스)로 실행
echo     (TFT 설정 ^> 비디오 ^> 창모드(보더리스))
echo  2. python calibrate.py  (좌표 확인)
echo  3. python main.py       (실행)
echo ====================================
pause
