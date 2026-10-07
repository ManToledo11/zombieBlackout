@echo off
python -m pip install --upgrade pygbag
python -m pygbag --archive zombie_blackout_web
echo.
echo Listo. Para itch.io sube: zombie_blackout_web\build\web.zip
echo Para otro hosting sube el contenido de: zombie_blackout_web\build\web
pause
