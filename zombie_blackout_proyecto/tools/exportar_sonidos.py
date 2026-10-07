"""Genera los sonidos del juego como archivos WAV en zombie_blackout_web/assets/sounds.

La versión web los carga ya hechos (en el navegador sintetizarlos tardaría varios segundos).
Ejecútalo de nuevo SOLO si cambias algún sonido del juego:

    pip install pygame
    python tools/exportar_sonidos.py
"""
import array
import json
import os
import sys
import wave

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")      # sin ventana ni audio real
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

AQUI = os.path.dirname(os.path.abspath(__file__))
JUEGO = os.path.normpath(os.path.join(AQUI, "..", "zombie_blackout_web"))
sys.path.insert(0, JUEGO)

import main as juego  # noqa: E402  (importar no ejecuta el juego)

muestras = []


def captura(samples, volume):
    muestras.append((list(samples), volume))
    return len(muestras) - 1                            # cada sonido devuelve su número de orden


def escribir_wav(ruta, samples):
    datos = array.array("h", [int(max(-1.0, min(1.0, x)) * 32000) for x in samples])
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(juego.SR)
        w.writeframes(datos.tobytes())


juego._SOUND_SINK = captura
recetas = juego.sound_recipes()

salida = os.path.join(JUEGO, "assets", "sounds")
os.makedirs(salida, exist_ok=True)
for viejo in os.listdir(salida):
    if viejo.endswith(".wav") or viejo == "sounds.json":
        os.remove(os.path.join(salida, viejo))

manifiesto, total = {}, 0
for nombre, valor in recetas.items():
    es_lista = isinstance(valor, list)
    indices = valor if es_lista else [valor]
    archivos, volumenes = [], []
    for i, idx in enumerate(indices):
        samples, vol = muestras[idx]
        fn = "%s%s.wav" % (nombre, "_%d" % i if es_lista else "")
        escribir_wav(os.path.join(salida, fn), samples)
        total += os.path.getsize(os.path.join(salida, fn))
        archivos.append(fn)
        volumenes.append(vol)
    manifiesto[nombre] = {"files": archivos, "vols": volumenes, "list": es_lista}

with open(os.path.join(salida, "sounds.json"), "w", encoding="utf-8") as f:
    json.dump(manifiesto, f, indent=1)
print("Listo: %d archivos WAV (%.2f MB) en %s" % (sum(len(v["files"]) for v in manifiesto.values()), total / 1e6, salida))
