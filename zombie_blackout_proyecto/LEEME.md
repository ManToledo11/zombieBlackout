# Zombie Blackout en el navegador

El juego ya está preparado para la web (pygbag). Hay tres formas de usarlo.

## A) Publicarlo gratis en GitHub Pages (recomendada, no instalas nada)
1. Crea un repositorio **público** en github.com.
2. Sube TODO el contenido de esta carpeta (incluida la carpeta oculta `.github`).
3. En el repositorio: **Settings → Pages → Source: "GitHub Actions"**.
4. Entra a la pestaña **Actions** y espera ~3 minutos a que termine "Publicar el juego en GitHub Pages".
5. Tu juego queda en `https://TU-USUARIO.github.io/NOMBRE-DEL-REPO/`.
Cada vez que subas un cambio, se vuelve a publicar solo.

## B) Publicarlo en itch.io
1. Ejecuta `construir_web.bat` (necesita Python).
2. En itch.io: *Create new project → Kind of project: HTML* → sube `zombie_blackout_web\build\web.zip`, marca
   "This file will be played in the browser" y pon tamaño 800 x 600. Itch.io trae botón de pantalla completa.

## C) Probarlo en tu PC antes de publicar
Ejecuta `probar_web.bat` y abre http://localhost:8000

## Notas
- La primera vez el navegador pide un clic para empezar (así habilita el sonido).
- Los puntajes y el volumen se guardan en el navegador de cada persona (no se comparten entre jugadores).
- Pantalla completa en la web: F11 del navegador (o el botón de itch.io). F11 / Alt+Enter dentro del juego solo funciona en PC.
- Si cambias algún sonido del juego, ejecuta `python tools/exportar_sonidos.py` para regenerar `assets/sounds`.
- Al ser público el repositorio, también lo son el código y `highscores.json`.
