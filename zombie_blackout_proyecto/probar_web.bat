@echo off
echo Instalando pygbag y probando el juego en http://localhost:8000 ...
python -m pip install --upgrade pygbag
python -m pygbag zombie_blackout_web
