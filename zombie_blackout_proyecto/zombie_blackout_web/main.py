#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZOMBIE BLACKOUT - HIGH SCORE EDITION
-----------------------------------------------------------------------
  - Cámara amplia y animaciones de ataque/recarga.
  - Tabla de mejores puntajes guardada automáticamente en JSON.
  - Registro de fecha, hora y dificultad segregada.
-----------------------------------------------------------------------
"""
import array
import asyncio
import json
import math
import os
import random
import sys
from datetime import datetime

import pygame

# ----------------------------------------------------------------------------
# Configuración Global
# ----------------------------------------------------------------------------
WIN_W, WIN_H = 800, 600
VIEW = pygame.Rect(40, 108, 720, 430)
VW, VH = VIEW.size
HORIZON = int(VH * 0.45)
FENCE_Z = 0.38
FENCE_Y1 = int(VH * 0.22)
FENCE_Y2 = int(VH * 0.77)
MAX_WAVES = 10
SR = 22050

ORANGE = (235, 140, 20)
RED = (200, 30, 25)
GOLD = (255, 215, 0)
CYAN = (0, 230, 255)
GREEN = (40, 220, 90)
SKY = (110, 195, 255)        # celeste del escudo
SILVER = (205, 205, 215)     # caja de reparar valla

MAX_SHIELD = 100.0
SHIELD_PER_BOX = 30.0
# Probabilidad relativa de cada recompensa: balas (la más común) > salud > escudo > valla (la más rara)
DROP_WEIGHTS = (("heavy_ammo", 50), ("health", 28), ("shield", 16), ("fence_repair", 6))
DROP_STYLE = {
    "heavy_ammo": (GOLD, "BALAS +"),
    "health": (GREEN, "+ SALUD"),
    "shield": (SKY, "ESCUDO +"),
    "fence_repair": (SILVER, "VALLA +"),
    "grenade": ((255, 110, 40), "GRANADA"),
}
GRENADE_CHANCE_PER_WAVE = 1.0   # probabilidad de que la oleada traiga su caja de granada (1.0 = una en cada oleada)
RELOAD_AUTO = 1.5               # recarga automática (cuando se acaban las balas), en segundos
RELOAD_MANUAL = 1.0             # recarga manual (tecla R), en segundos

pygame.mixer.pre_init(SR, -16, 1, 512)
pygame.init()
try:
    pygame.mixer.init(SR, -16, 1, 512)
    MIXER_OK = True
except pygame.error:
    MIXER_OK = False

if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: __file__ apunta a una carpeta TEMPORAL que se borra al cerrar el juego.
    BASE_DIR = os.path.dirname(sys.executable)         # carpeta del .exe: aquí se guardan los puntajes
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)       # recursos empaquetados dentro del .exe
else:
    BASE_DIR = RES_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(RES_DIR, "assets")
HIGHSCORE_FILE = os.path.join(BASE_DIR, "highscores.json")     # puntajes del jugador (se escribe aquí)
SEED_FILE = os.path.join(RES_DIR, "highscores.json")           # puntajes iniciales empaquetados (opcional)
FENCE_REPAIR_TIME = 4.0

# ¿Corre dentro de un navegador (pygbag/WebAssembly)? Ahí no hay "salir" ni archivos permanentes.
IS_WEB = sys.platform == "emscripten"
STORE_KEY = "zombie_blackout_highscores"
MENU_N = 3 if IS_WEB else 4      # filas del menú: ..., VOLUMEN, SALIR (en la web no existe SALIR)
VOL_IDX = 2                      # posición de la fila de volumen en todos los menús
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
SETTINGS_KEY = "zombie_blackout_settings"
FONT_WEB = os.path.join(ASSET_DIR, "DejaVuSansCondensed-Bold.ttf")
SOUND_DIR = os.path.join(ASSET_DIR, "sounds")


# ----------------------------------------------------------------------------
# Gestión de Mejores Puntajes (High Scores)
# ----------------------------------------------------------------------------
_SCORES_CACHE = None


def _local_storage():
    """localStorage del navegador (solo existe en la versión web)."""
    if not IS_WEB:
        return None
    try:
        import platform
        return platform.window.localStorage
    except Exception:
        return None


def _read_scores_file(path):
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def load_high_scores():
    """Devuelve los puntajes ordenados de mayor a menor (con caché para no leer en cada fotograma)."""
    global _SCORES_CACHE
    if _SCORES_CACHE is not None:
        return _SCORES_CACHE
    data = []
    ls = _local_storage()
    if ls is not None:
        try:
            raw = ls.getItem(STORE_KEY)
            if raw:
                data = json.loads(str(raw))
        except Exception:
            data = []
        if not data:                      # primera vez en este navegador: usa los puntajes incluidos
            data = _read_scores_file(HIGHSCORE_FILE)
    else:
        data = _read_scores_file(HIGHSCORE_FILE) or _read_scores_file(SEED_FILE)
    data = [d for d in data if isinstance(d, dict) and "score" in d]
    for item in data:
        item.setdefault("difficulty", "medio")
    data.sort(key=lambda x: x["score"], reverse=True)
    _SCORES_CACHE = data
    return data


def save_high_score(score, name="???", difficulty="medio"):
    """Guarda un nuevo puntaje con nombre, dificultad y fecha/hora (archivo en PC, localStorage en la web)."""
    global _SCORES_CACHE
    if score <= 0:
        return
    scores = list(load_high_scores())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    clean_name = (name or "???").strip()[:20] or "???"
    scores.append({"name": clean_name, "score": int(score), "difficulty": difficulty, "date": now_str})
    scores.sort(key=lambda x: x["score"], reverse=True)
    _SCORES_CACHE = scores
    try:
        ls = _local_storage()
        if ls is not None:
            ls.setItem(STORE_KEY, json.dumps(scores))
        else:
            with open(HIGHSCORE_FILE, "w", encoding="utf-8") as f:
                json.dump(scores, f, indent=2)
    except Exception:
        pass


def load_volume(default=0.7):
    """Volumen guardado (0.0 a 1.0): archivo junto al juego en PC, localStorage en la web."""
    try:
        ls = _local_storage()
        if ls is not None:
            raw = ls.getItem(SETTINGS_KEY)
        elif os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = None
        if raw:
            v = float(json.loads(str(raw)).get("volume", default))
            return max(0.0, min(1.0, round(v * 10) / 10))
    except Exception:
        pass
    return default


def save_volume(v):
    try:
        data = json.dumps({"volume": v})
        ls = _local_storage()
        if ls is not None:
            ls.setItem(SETTINGS_KEY, data)
        else:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                f.write(data)
    except Exception:
        pass


def load_image(filename, size):
    path = os.path.join(ASSET_DIR, filename)
    if not os.path.isfile(path):
        return None
    try:
        img = pygame.image.load(path).convert_alpha()
        if img.get_size() != size:
            img = pygame.transform.smoothscale(img, size)
        return img
    except Exception:
        return None


DIFFICULTIES = {
    "facil": {"name": "FÁCIL", "hp": 0.75, "speed": 0.8, "brute": 0.05, "count": 0.8, "dmg": 0.7},
    "medio": {"name": "MEDIO", "hp": 1.0, "speed": 1.0, "brute": 0.15, "count": 1.0, "dmg": 1.0},
    "dificil": {"name": "DIFÍCIL", "hp": 1.35, "speed": 1.25, "brute": 0.30, "count": 1.25, "dmg": 1.4},
    "bestia": {"name": "MODO BESTIA", "hp": 2.2, "speed": 1.7, "brute": 0.55, "count": 1.6, "dmg": 2.2},
}


# ----------------------------------------------------------------------------
# Generador de Sonidos Procedurales
# ----------------------------------------------------------------------------
_SOUND_SINK = None   # herramienta de exportación (tools/exportar_sonidos.py): si existe, recibe (muestras, volumen)


def to_sound(samples, volume=1.0):
    if _SOUND_SINK is not None:
        return _SOUND_SINK(samples, volume)
    if not MIXER_OK:
        return None
    buf = array.array("h", [int(max(-1.0, min(1.0, s)) * 32000) for s in samples])
    snd = pygame.mixer.Sound(buffer=buf.tobytes())
    snd.set_volume(volume)
    return snd


def make_shot():
    out, lp = [], 0.0
    for i in range(int(SR * 0.45)):
        t = i / SR
        noise = random.uniform(-1, 1)
        lp += (noise - lp) * 0.30
        crack = noise * math.exp(-t * 70)
        boom = lp * 1.5 * math.exp(-t * 8)
        thump = math.sin(2 * math.pi * (70 - 40 * t) * t) * math.exp(-t * 11)
        out.append((crack * 0.6 + boom + thump * 0.9) * 0.85)
    return to_sound(out, 0.85)


def make_heavy_shot():
    out, lp = [], 0.0
    for i in range(int(SR * 0.65)):
        t = i / SR
        noise = random.uniform(-1, 1)
        lp += (noise - lp) * 0.15
        boom = lp * 2.8 * math.exp(-t * 5)
        blast = math.sin(2 * math.pi * (120 - 80 * t) * t) * math.exp(-t * 7)
        echo = noise * math.exp(-t * 25) * 0.7
        out.append((boom + blast * 1.2 + echo) * 0.9)
    return to_sound(out, 1.0)


def make_groan(base, dur, drop=0.15, vol=0.6):
    out, phase, lp = [], 0.0, 0.0
    for i in range(int(SR * dur)):
        t = i / SR
        f = base * (1 + 0.10 * math.sin(2 * math.pi * 5.5 * t)) * (1 - drop * t / dur)
        phase += 2 * math.pi * f / SR
        v = sum(math.sin(k * phase) / k for k in range(1, 6))
        lp += (random.uniform(-1, 1) - lp) * 0.2
        env = math.sin(math.pi * t / dur) ** 0.7
        out.append((v * 0.22 + lp * 0.25) * env)
    return to_sound(out, vol)


def make_hit():
    out, phase, lp = [], 0.0, 0.0
    for i in range(int(SR * 0.2)):
        t = i / SR
        phase += 2 * math.pi * (40 + 120 * math.exp(-t * 14)) / SR
        lp += (random.uniform(-1, 1) - lp) * 0.4
        out.append(math.sin(phase) * math.exp(-t * 16) * 0.9 + lp * math.exp(-t * 28) * 0.6)
    return to_sound(out, 0.8)


def make_hurt():
    out, phase, lp = [], 0.0, 0.0
    for i in range(int(SR * 0.4)):
        t = i / SR
        phase += 2 * math.pi * (45 + 60 * math.exp(-t * 6)) / SR
        lp += (random.uniform(-1, 1) - lp) * 0.15
        out.append((math.sin(phase) * 0.9 + lp * 0.5) * math.exp(-t * 7))
    return to_sound(out, 0.9)


def make_fence_break():
    out, lp = [], 0.0
    for i in range(int(SR * 0.3)):
        t = i / SR
        noise = random.uniform(-1, 1)
        lp += (noise - lp) * 0.5
        snap = math.sin(2 * math.pi * (400 - 200 * t) * t) * math.exp(-t * 30)
        out.append((lp * 0.7 + snap * 0.8) * math.exp(-t * 10))
    return to_sound(out, 0.85)


def make_shield_hit():
    out = []
    for i in range(int(SR * 0.22)):
        t = i / SR
        ring = (math.sin(2 * math.pi * 880 * t) + 0.6 * math.sin(2 * math.pi * 1320 * t)) * math.exp(-t * 18)
        zap = random.uniform(-1, 1) * math.exp(-t * 60) * 0.5
        out.append((ring * 0.5 + zap) * 0.8)
    return to_sound(out, 0.7)


def make_boom():
    out, fase = [], 0.0
    for i in range(int(SR * 0.9)):
        t = i / SR
        fase += 2 * math.pi * (45 + 90 * math.exp(-t * 8)) / SR      # golpe grave que cae de tono
        thump = math.sin(fase) * math.exp(-t * 4)
        noise = random.uniform(-1, 1) * math.exp(-t * 7)
        out.append(0.8 * thump + 0.55 * noise)
    return to_sound(out, 0.9)


def make_click():
    out, lp = [], 0.0
    for i in range(int(SR * 0.05)):
        t = i / SR
        lp += (random.uniform(-1, 1) - lp) * 0.6
        out.append(lp * math.exp(-t * 110))
    return to_sound(out, 0.7)


def make_reload():
    out, lp = [], 0.0
    hits = [(0.1, 0.8), (0.7, 1.0), (1.1, 0.9)]
    for i in range(int(SR * 1.4)):
        t = i / SR
        lp += (random.uniform(-1, 1) - lp) * 0.45
        v = 0.0
        for t0, a in hits:
            if t >= t0:
                e = math.exp(-(t - t0) * 50) * a
                v += (lp * 0.8 + math.sin(2 * math.pi * 220 * (t - t0)) * 0.5) * e
        out.append(v * 0.7)
    return to_sound(out, 0.8)


def make_powerup_sound():
    out = []
    for i in range(int(SR * 0.35)):
        t = i / SR
        f = 440 + 880 * (t / 0.35)
        v = math.sin(2 * math.pi * f * t) * math.exp(-t * 4)
        out.append(v * 0.8)
    return to_sound(out, 0.85)


def make_wind():
    dur = 3.0
    n = int(SR * dur)
    out, lp = [], 0.0
    for i in range(n):
        t = i / SR
        lp += (random.uniform(-1, 1) - lp) * 0.02
        mod = 0.6 + 0.4 * math.sin(2 * math.pi * 0.33 * t)
        fade = min(1.0, t / 0.4, (dur - t) / 0.4)
        out.append(lp * 3.0 * mod * fade)
    return to_sound(out, 0.35)


# ----------------------------------------------------------------------------
# Clase DropItem
# ----------------------------------------------------------------------------
class DropItem:
    def __init__(self, x, y, drop_type):
        self.x = x
        self.y = y
        self.type = drop_type
        self.t = 0.0
        self.life = 9.0
        self.radius = 12                                   # cajas más pequeñas
        self.vy = 0.0
        self.ground_y = max(y, FENCE_Y2 - self.radius)     # suelo de la valla
        self.landed = y >= self.ground_y

    def update(self, dt):
        self.t += dt
        self.life -= dt
        if not self.landed:
            self.vy = min(150.0, self.vy + 260.0 * dt)     # desciende despacio, acelerando un poco
            self.y += self.vy * dt
            if self.y >= self.ground_y:
                self.y = self.ground_y
                self.landed = True
                self.vy = 0.0

    def is_expired(self):
        return self.life <= 0

    def hit_test(self, px, py):
        return math.hypot(px - self.x, py - self.y) <= self.radius + 10

    def draw(self, surf, font):
        if self.life < 1.8 and int(self.t * 8) % 2 == 0:   # parpadea antes de desaparecer
            return
        float_y = self.y + (math.sin(self.t * 4) * 2 if self.landed else 0.0)
        pulse = 1.0 + 0.12 * math.sin(self.t * 8)
        r = int(self.radius * pulse)
        col, text_str = DROP_STYLE[self.type]

        glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, 70), (r * 2, r * 2), r * 2)
        surf.blit(glow, (int(self.x - r * 2), int(float_y - r * 2)))

        rect = pygame.Rect(self.x - r, float_y - r, r * 2, r * 2)
        pygame.draw.rect(surf, (20, 20, 20), rect, border_radius=4)
        pygame.draw.rect(surf, col, rect, width=2, border_radius=4)

        # icono dentro de la caja
        cx, cy, k = int(self.x), int(float_y), max(2, r // 3)
        if self.type == "health":
            pygame.draw.rect(surf, col, (cx - 1, cy - k, 3, 2 * k + 1))
            pygame.draw.rect(surf, col, (cx - k, cy - 1, 2 * k + 1, 3))
        elif self.type == "shield":
            pygame.draw.polygon(surf, col, [(cx - k, cy - k), (cx + k, cy - k), (cx + k, cy),
                                            (cx, cy + k + 1), (cx - k, cy)])
        elif self.type == "heavy_ammo":
            pygame.draw.rect(surf, col, (cx - 1, cy - k + 2, 3, 2 * k - 2))
            pygame.draw.circle(surf, col, (cx, cy - k + 2), 2)
        elif self.type == "grenade":
            pygame.draw.circle(surf, col, (cx, cy + 1), k + 1)
            pygame.draw.rect(surf, col, (cx - 1, cy - k - 2, 3, 3))
        else:
            pygame.draw.line(surf, col, (cx - k, cy - k), (cx + k, cy + k), 2)
            pygame.draw.line(surf, col, (cx + k, cy - k), (cx - k, cy + k), 2)

        lbl = font.render(text_str, True, col)
        surf.blit(lbl, (self.x - lbl.get_width() // 2, float_y - r - 14))


# ----------------------------------------------------------------------------
# Clase Zombie
# ----------------------------------------------------------------------------
class Zombie:
    def __init__(self, speed, diff_cfg, is_brute=False):
        self.is_brute = is_brute
        self.nx = random.uniform(0.08, 0.92)
        self.z = 1.0
        self.speed = speed * diff_cfg["speed"] * (0.60 if is_brute else 1.0)
        self.wounds = []

        base_hp = (10 if is_brute else 3) * diff_cfg["hp"]
        self.max_hp = base_hp
        self.hp = base_hp
        self.scale_mult = 1.35 if is_brute else 1.0
        self.damage_value = int((30 if is_brute else 12) * diff_cfg["dmg"])

        if self.is_brute:
            self.c_base = (42, 18, 55)
            self.c_base_dark = (28, 10, 38)
            self.c_armor = (18, 18, 22)
            self.c_armor_light = (32, 32, 38)
            self.c_accent = (220, 20, 35)
            self.c_eye = (255, 50, 40)
        else:
            self.c_base = (58, 92, 52)
            self.c_base_dark = (38, 64, 34)
            self.c_armor = (42, 48, 46)
            self.c_armor_light = (65, 72, 70)
            self.c_accent = (215, 195, 55)
            self.c_eye = (245, 230, 60)

        self.phase = random.uniform(0, 6.28)
        self.t = 0.0
        self.atk_timer = 0.0
        self.fall = 0.0
        self.hit_flash = 0.0

        self.stumble_t = 0.0
        self.flinch_t = 0.0

        self.state = "walk"
        self.climb_t = 0.0
        self.climb_dur = 3.0 if not is_brute else 3.6
        self.break_hits_needed = 2 if is_brute else 4    # golpes para romper la valla (bruto 2, normal 4)
        self.break_interval = 0.6 if not is_brute else 0.5
        self.break_hits_done = 0
        self.break_timer = 0.0
        self.fence_shake = 0.0
        self.crack_seed = random.randint(0, 99999)
        self.fence_action_chosen = False
        self.crossed = False

    @property
    def alive(self):
        return self.hp > 0

    @property
    def done(self):
        return self.hp <= 0 and self.fall > 0.7

    def add_wound(self, part, px, py):
        cx, fy, h = self.geom()
        hr = max(3, int(h * (0.11 if self.is_brute else 0.095)))
        hip_y = fy - h * 0.40
        torso_h = h * 0.38
        torso_y = hip_y - torso_h

        if part == "head":
            center_x, center_y = cx, torso_y - hr * 0.8
        elif part in ("stomach", "arm"):
            center_x, center_y = cx, torso_y + torso_h / 2
        else:
            center_x, center_y = cx, hip_y + h * 0.2

        rx = (px - center_x) / h
        ry = (py - center_y) / h
        size = random.uniform(2.5, 4.5)
        self.wounds.append((part, rx, ry, size))

    def update(self, dt, game):
        self.t += dt
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.fence_shake = max(0.0, self.fence_shake - dt)
        self.flinch_t = max(0.0, self.flinch_t - dt)

        if not self.alive:
            self.fall += dt
            return

        if self.stumble_t > 0:
            self.stumble_t -= dt
            return

        if self.flinch_t > 0:
            return

        if self.state == "walk":
            if self.z > FENCE_Z:
                self.z = max(FENCE_Z, self.z - self.speed * dt)
                if self.z <= FENCE_Z:
                    self.state = "at_fence"
            else:
                self.z = max(0.09, self.z - self.speed * dt)
                if self.z <= 0.09:
                    self.state = "attack"

        elif self.state == "at_fence":
            if not self.fence_action_chosen:
                if game.check_fence_hole(self.nx):        # ya hay un hueco: pasa directo
                    self.state = "walk"
                    self.z -= 0.01
                    self.crossed = True
                elif self.is_brute or random.random() < 0.5:   # bruto: siempre rompe; normal: la mitad rompe
                    self.state = "breaking_fence"
                    self.break_timer = 0.0
                else:                                      # la otra mitad de los normales trepa
                    self.state = "climbing"
                    self.climb_t = 0.0
                self.fence_action_chosen = True

        elif self.state == "climbing":
            self.climb_t += dt
            if not self.crossed and (self.climb_t / self.climb_dur) >= 0.75:
                self.crossed = True
            if self.climb_t >= self.climb_dur:
                self.state = "walk"
                self.z = FENCE_Z - 0.03

        elif self.state == "breaking_fence":
            if game.check_fence_hole(self.nx):            # otro zombi ya abrió un hueco aquí
                self.state = "walk"
                self.z = FENCE_Z - 0.02
                self.crossed = True
                return
            self.break_timer += dt
            if self.break_timer >= self.break_interval:
                self.break_timer = 0.0
                self.break_hits_done += 1
                self.fence_shake = 0.3
                if self.break_hits_done >= self.break_hits_needed:
                    game.break_fence(self)                # último golpe: la valla se rompe
                    self.state = "walk"
                    self.z = FENCE_Z - 0.02
                    self.crossed = True
                else:
                    game.fence_hit(self)                  # golpes anteriores: grietas

        elif self.state == "attack":
            self.atk_timer += dt
            if self.atk_timer >= 0.8:
                self.atk_timer = 0.0
                game.damage_player(self.damage_value)

    def geom(self):
        k = 1.0 - self.z
        s = (0.16 + 0.58 * (k ** 1.1)) * self.scale_mult
        h = 280 * s
        fy_base = HORIZON + 15 + (VH - HORIZON - 20) * (k ** 1.1)

        offset_y = 0.0
        if self.state == "climbing":
            p = self.climb_t / self.climb_dur
            top_y = VH * 0.06
            full_rise = max(fy_base - h - top_y, h * 0.9)
            if p < 0.55:
                offset_y = -full_rise * (p / 0.55)
            elif p < 0.75:
                offset_y = -full_rise
            else:
                fall_p = (p - 0.75) / 0.25
                offset_y = -full_rise * (1.0 - fall_p)

        elif self.stumble_t > 0:
            offset_y = h * 0.20 * min(1.0, self.stumble_t)

        if not self.alive:
            h *= max(0.06, 1.0 - self.fall * 1.4)

        fy = fy_base + offset_y
        sway_amount = 10 if self.is_brute else 6
        cx = VW * (0.10 + 0.80 * self.nx) + math.sin(self.t * 1.6 + self.phase) * sway_amount * s
        return cx, fy, h

    def hit_test(self, px, py, tol=8):
        if not self.alive:
            return None
        cx, fy, h = self.geom()
        w = h * (0.52 if self.is_brute else 0.38)
        hr = h * 0.11 + tol

        if math.hypot(px - cx, py - (fy - h * 0.86)) <= hr:
            return "head"

        hip_y = fy - h * 0.40
        torso_h = h * 0.38
        torso_y = hip_y - torso_h

        if (cx - w * 0.75 - tol <= px <= cx + w * 0.75 + tol) and (torso_y <= py <= hip_y):
            if px < cx - w * 0.35 or px > cx + w * 0.35:
                return "arm"
            return "stomach"

        if (cx - w * 0.5 - tol <= px <= cx + w * 0.5 + tol) and (hip_y < py <= fy + tol):
            return "leg"

        return None

    def draw(self, surf, eyes):
        cx, fy, h = self.geom()
        w = h * (0.54 if self.is_brute else 0.38)
        shade = 1.0 if self.hit_flash <= 0 else 1.8

        def adj(c):
            return tuple(min(255, int(v * shade)) for v in c)

        c_base = adj(self.c_base)
        c_base_dark = adj(self.c_base_dark)
        c_armor = adj(self.c_armor)
        c_armor_light = adj(self.c_armor_light)
        c_accent = adj(self.c_accent)

        walk_speed = 6.0 if not self.is_brute else 4.2
        leg_cycle = math.sin(self.t * walk_speed + self.phase) if self.state == "walk" and self.stumble_t <= 0 else 0.0
        arm_cycle = math.sin(self.t * walk_speed + self.phase) if self.state == "walk" else 0.0

        if self.alive:
            sw_w, sw_h = max(6, int(w * 0.95)), max(3, int(w * 0.3))
            s_surf = pygame.Surface((sw_w, sw_h), pygame.SRCALPHA)
            pygame.draw.ellipse(s_surf, (0, 0, 0, 110), (0, 0, sw_w, sw_h))
            surf.blit(s_surf, (int(cx - sw_w / 2), int(fy - sw_h / 2)))

        hip_y = fy - h * 0.38
        torso_h = h * 0.38
        torso_y = hip_y - torso_h

        # Piernas
        leg_stride = leg_cycle * h * 0.12
        for side in (-1, 1):
            ls = leg_stride if side == 1 else -leg_stride
            hip_p = (cx + side * w * 0.22, hip_y)
            knee_p = (cx + side * w * 0.26 + ls * 0.5, hip_y + h * 0.20)
            foot_p = (cx + side * w * 0.24 + ls, fy)

            thigh_poly = [
                (hip_p[0] - w * 0.08, hip_p[1]),
                (hip_p[0] + w * 0.08, hip_p[1]),
                (knee_p[0] + w * 0.06, knee_p[1]),
                (knee_p[0] - w * 0.06, knee_p[1]),
            ]
            pygame.draw.polygon(surf, c_armor if side == 1 else c_base_dark, thigh_poly)

            calf_poly = [
                (knee_p[0] - w * 0.06, knee_p[1]),
                (knee_p[0] + w * 0.06, knee_p[1]),
                (foot_p[0] + w * 0.08, foot_p[1]),
                (foot_p[0] - w * 0.08, foot_p[1]),
            ]
            pygame.draw.polygon(surf, c_base if side == 1 else c_armor_light, calf_poly)

            foot_poly = [
                (foot_p[0] - w * 0.08, foot_p[1]),
                (foot_p[0] + w * 0.08, foot_p[1]),
                (foot_p[0] + side * w * 0.12, foot_p[1] + h * 0.03),
            ]
            pygame.draw.polygon(surf, c_accent if self.is_brute else c_armor, foot_poly)

        # Torso
        center_torso = [
            (cx - w * 0.32, torso_y),
            (cx + w * 0.32, torso_y),
            (cx + w * 0.22, hip_y),
            (cx - w * 0.22, hip_y),
        ]
        pygame.draw.polygon(surf, c_base, center_torso)

        chest_plate_top = [
            (cx, torso_y + torso_h * 0.1),
            (cx - w * 0.38, torso_y + torso_h * 0.25),
            (cx, torso_y + torso_h * 0.55),
            (cx + w * 0.38, torso_y + torso_h * 0.25),
        ]
        pygame.draw.polygon(surf, c_armor, chest_plate_top)

        chest_plate_bot = [
            (cx, torso_y + torso_h * 0.50),
            (cx - w * 0.28, torso_y + torso_h * 0.70),
            (cx, torso_y + torso_h * 0.95),
            (cx + w * 0.28, torso_y + torso_h * 0.70),
        ]
        pygame.draw.polygon(surf, c_armor_light if not self.is_brute else c_base_dark, chest_plate_bot)

        if self.is_brute:
            for s_dir in (-1, 1):
                spike_shoulder = [
                    (cx + s_dir * w * 0.38, torso_y + torso_h * 0.1),
                    (cx + s_dir * w * 0.65, torso_y - torso_h * 0.25),
                    (cx + s_dir * w * 0.48, torso_y + torso_h * 0.35),
                ]
                pygame.draw.polygon(surf, c_accent, spike_shoulder)

        # Brazos
        shoulder_y = torso_y + torso_h * 0.15
        for side in (-1, 1):
            a_off = (arm_cycle if side == 1 else -arm_cycle) * h * 0.08

            if self.state == "attack":
                reach = math.sin(self.atk_timer * 15) * h * 0.1
                elbow = (cx + side * w * 0.68, shoulder_y - h * 0.05 + reach)
                hand = (cx + side * w * 0.85, shoulder_y + h * 0.10 - reach)
            elif self.state == "climbing":
                p = self.climb_t / self.climb_dur
                arm_reach = -h * 0.25 if p < 0.6 else 0.0
                elbow = (cx + side * w * 0.55, shoulder_y + arm_reach * 0.5)
                hand = (cx + side * w * 0.45, shoulder_y + arm_reach)
            elif self.state == "breaking_fence":
                # levanta los brazos poco a poco y golpea la valla de golpe
                p = self.break_timer / self.break_interval
                amt = p / 0.8 if p < 0.8 else max(0.0, 1.0 - (p - 0.8) / 0.2)
                elbow = (cx + side * w * 0.55, shoulder_y + h * (0.16 - 0.21 * amt))
                hand = (cx + side * w * (0.48 - 0.10 * amt), shoulder_y + h * (0.32 - 0.52 * amt))
            elif self.flinch_t > 0:
                elbow = (cx + side * w * 0.60, shoulder_y - h * 0.10)
                hand = (cx + side * w * 0.50, shoulder_y - h * 0.20)
            else:
                elbow = (cx + side * w * 0.52, shoulder_y + h * 0.16 + a_off)
                hand = (cx + side * w * 0.48 + side * h * 0.04, shoulder_y + h * 0.32 - a_off)

            b1 = [
                (cx + side * w * 0.32, shoulder_y),
                (elbow[0] + w * 0.08, elbow[1] - h * 0.02),
                (elbow[0] - w * 0.08, elbow[1] + h * 0.02),
            ]
            pygame.draw.polygon(surf, c_base if side == 1 else c_base_dark, b1)

            b2 = [
                (elbow[0] - w * 0.07, elbow[1]),
                (elbow[0] + w * 0.07, elbow[1]),
                (hand[0] + w * 0.09, hand[1]),
                (hand[0] - w * 0.09, hand[1]),
            ]
            pygame.draw.polygon(surf, c_armor if side == -1 else c_armor_light, b2)

            claw_color = c_accent if self.is_brute else c_armor_light
            for finger in (-0.06, 0.0, 0.06):
                claw_poly = [
                    (hand[0] + finger * w, hand[1]),
                    (hand[0] + (finger + 0.03 * side) * w, hand[1] + h * 0.08),
                    (hand[0] + (finger - 0.02) * w, hand[1] + h * 0.02),
                ]
                pygame.draw.polygon(surf, claw_color, claw_poly)

        # Cabeza
        hr = max(5, int(h * (0.12 if self.is_brute else 0.10)))
        head_cx = int(cx)
        head_cy = int(torso_y - hr * 0.85)

        head_poly = [
            (head_cx - hr * 0.8, head_cy - hr * 0.5),
            (head_cx, head_cy - hr * 1.1),
            (head_cx + hr * 0.8, head_cy - hr * 0.5),
            (head_cx + hr * 1.0, head_cy + hr * 0.3),
            (head_cx + hr * 0.5, head_cy + hr * 0.9),
            (head_cx - hr * 0.5, head_cy + hr * 0.9),
            (head_cx - hr * 1.0, head_cy + hr * 0.3),
        ]
        pygame.draw.polygon(surf, c_base, head_poly)

        mouth_open = 0.5
        if self.state == "attack":
            mouth_open = 0.5 + 0.55 * abs(math.sin(self.atk_timer * 16))

        jaw_offset = hr * 0.4 * mouth_open
        jaw_poly = [
            (head_cx - hr * 0.7, head_cy + hr * 0.1),
            (head_cx + hr * 0.7, head_cy + hr * 0.1),
            (head_cx, head_cy + hr * 1.0 + jaw_offset),
        ]
        pygame.draw.polygon(surf, c_armor, jaw_poly)

        mouth_poly = [
            (head_cx - hr * 0.5, head_cy + hr * 0.25),
            (head_cx + hr * 0.5, head_cy + hr * 0.25),
            (head_cx, head_cy + hr * (0.6 + 0.7 * mouth_open)),
        ]
        pygame.draw.polygon(surf, (15, 5, 5), mouth_poly)

        teeth_col = (245, 240, 200) if not self.is_brute else (220, 220, 220)
        for tooth_x in (-0.3, 0.0, 0.3):
            t_poly_top = [
                (head_cx + tooth_x * hr - hr * 0.08, head_cy + hr * 0.25),
                (head_cx + tooth_x * hr + hr * 0.08, head_cy + hr * 0.25),
                (head_cx + tooth_x * hr, head_cy + hr * 0.45),
            ]
            pygame.draw.polygon(surf, teeth_col, t_poly_top)

            t_poly_bot = [
                (head_cx + tooth_x * hr - hr * 0.08, head_cy + hr * (0.6 + 0.5 * mouth_open)),
                (head_cx + tooth_x * hr + hr * 0.08, head_cy + hr * (0.6 + 0.5 * mouth_open)),
                (head_cx + tooth_x * hr, head_cy + hr * (0.42 + 0.4 * mouth_open)),
            ]
            pygame.draw.polygon(surf, teeth_col, t_poly_bot)

        if self.alive:
            er = max(2, int(hr * 0.26))
            for ex_dir in (-0.38, 0.38):
                eye_x = int(head_cx + ex_dir * hr)
                eye_y = int(head_cy - hr * 0.2)
                eyes.append((eye_x, eye_y, er, adj(self.c_eye)))

        for part, rx, ry, wound_size in self.wounds:
            ws = max(2, int(wound_size * (h / 200.0)))
            if part == "head":
                wx, wy = int(head_cx + rx * h), int(head_cy + ry * h)
            else:
                wx, wy = int(cx + rx * h), int((torso_y + torso_h / 2) + ry * h)

            w_poly = [
                (wx - ws, wy),
                (wx, wy - ws * 1.2),
                (wx + ws, wy),
                (wx, wy + ws * 1.2),
            ]
            pygame.draw.polygon(surf, (180, 10, 15), w_poly)


# ----------------------------------------------------------------------------
# Clase Principal del Juego
# ----------------------------------------------------------------------------
def sound_recipes():
    """Todos los sonidos del juego, sintetizados desde cero."""
    return {
        "shot": make_shot(),
        "heavy_shot": make_heavy_shot(),
        "hit": make_hit(),
        "hurt": make_hurt(),
        "fence_break": make_fence_break(),
        "shield_hit": make_shield_hit(),
        "boom": make_boom(),
        "click": make_click(),
        "reload": make_reload(),
        "powerup": make_powerup_sound(),
        "wind": make_wind(),
        "groan": [make_groan(b, d) for b, d in ((62, 1.2), (78, 1.0), (92, 0.9))],
        "die": make_groan(120, 0.9, drop=0.55, vol=0.75),
    }


def load_prerendered_sounds():
    """Carga los WAV de assets/sounds (los crea tools/exportar_sonidos.py). Devuelve None si no están."""
    try:
        with open(os.path.join(SOUND_DIR, "sounds.json"), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        out = {}
        for name, info in manifest.items():
            items = []
            for fn, vol in zip(info["files"], info["vols"]):
                snd = pygame.mixer.Sound(os.path.join(SOUND_DIR, fn)) if MIXER_OK else None
                if snd:
                    snd.set_volume(vol)
                items.append(snd)
            out[name] = items if info["list"] else items[0]
        return out
    except Exception:
        return None


class Game:
    def __init__(self):
        self.scaled = not IS_WEB             # en PC se dibuja en un lienzo fijo y se escala a la ventana
        self.fullscreen = False
        if self.scaled:
            pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
            self.screen = pygame.Surface((WIN_W, WIN_H))
        else:
            self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("ZOMBIE BLACKOUT - ULTIMATE EDITION")
        self.clock = pygame.time.Clock()

        if IS_WEB or os.path.isfile(FONT_WEB) and not pygame.font.match_font("arial"):
            self.f_title = pygame.font.Font(FONT_WEB, 36)
            self.f_big = pygame.font.Font(FONT_WEB, 28)
            self.f_mid = pygame.font.Font(FONT_WEB, 16)
            self.f_small = pygame.font.Font(FONT_WEB, 12)
        else:
            self.f_title = pygame.font.SysFont("impact,arialblack,arial", 38)
            self.f_big = pygame.font.SysFont("impact,arialblack,arial", 30)
            self.f_mid = pygame.font.SysFont("arial", 17, bold=True)
            self.f_small = pygame.font.SysFont("arial", 12, bold=True)

        self.fence_holes = []
        self.drops = []
        self.difficulty = "medio"
        self.beast_unlocked = False
        self.player_name = ""
        self.name_input = ""
        self.score_tab = "todos"  # Pestaña seleccionada en el scoreboard

        self.build_graphics()
        self.loading_screen()
        self.build_sounds()

        self.state = "name_entry"   # primero pide el nombre, luego pasa al menú
        self.started = False
        self.menu_sel = 0
        self.reset()
        self.light = [VW / 2, VH / 2]

    def loading_screen(self):
        self.screen.fill((20, 8, 5))
        t = self.f_big.render("CARGANDO SONIDOS...", True, ORANGE)
        self.screen.blit(t, (WIN_W // 2 - t.get_width() // 2, WIN_H // 2 - t.get_height() // 2))
        self.present()
        pygame.event.pump()

    # ---------- escalado y pantalla completa ----------
    def view_transform(self):
        """(escala, desplazamiento x, desplazamiento y, ancho, alto) del lienzo dentro de la ventana."""
        if not self.scaled:
            return 1.0, 0, 0, WIN_W, WIN_H
        ww, wh = pygame.display.get_surface().get_size()
        sc = min(ww / WIN_W, wh / WIN_H) if ww > 0 and wh > 0 else 1.0
        w, h = max(1, int(WIN_W * sc)), max(1, int(WIN_H * sc))
        return sc, (ww - w) // 2, (wh - h) // 2, w, h

    def to_canvas(self, pos):
        """Convierte una posición de la ventana a coordenadas del lienzo de 800x600."""
        sc, ox, oy, _, _ = self.view_transform()
        return int((pos[0] - ox) / sc), int((pos[1] - oy) / sc)

    def mouse_pos(self):
        return self.to_canvas(pygame.mouse.get_pos())

    def present(self):
        """Muestra el lienzo en la ventana, escalado y centrado (con franjas negras si cambia la proporción)."""
        if self.scaled:
            win = pygame.display.get_surface()
            _, ox, oy, w, h = self.view_transform()
            win.fill((0, 0, 0))
            if (w, h) == (WIN_W, WIN_H):
                win.blit(self.screen, (ox, oy))
            else:
                win.blit(pygame.transform.smoothscale(self.screen, (w, h)), (ox, oy))
        pygame.display.flip()

    def toggle_fullscreen(self):
        if not self.scaled:
            return
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)

    def quit_game(self):
        """En PC cierra el juego; en el navegador no se puede cerrar, así que vuelve al menú."""
        if IS_WEB:
            self.state = "menu"
            self.started = False
            pygame.mouse.set_visible(True)
            return
        pygame.quit()
        sys.exit()

    def build_graphics(self):
        random.seed(7)

        custom_bg = load_image("background.png", (VW, VH))
        self.bg = custom_bg if custom_bg else self._build_bg_procedural()
        self._apply_grade(self.bg)

        custom_fence = load_image("fence.png", (VW, VH))
        self.fence_base = custom_fence if custom_fence else self._build_fence_procedural()
        self.rebuild_fence_surface()

        R = 240
        hole = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        for r in range(R, 0, -2):
            a = int(215 * (1 - r / R) ** 0.55)
            pygame.draw.circle(hole, (0, 0, 0, a), (R, R), r)
        self.hole, self.hole_r = hole, R
        self.dark = pygame.Surface((VW, VH), pygame.SRCALPHA)

        frame = pygame.Surface((WIN_W, WIN_H))
        frame.fill((26, 9, 6))
        for y in range(104):
            f = y / 104
            pygame.draw.line(frame, (int(150 - 90 * f), int(55 - 35 * f), int(10 - 5 * f)), (0, y), (WIN_W, y))
        pygame.draw.rect(frame, (90, 40, 20), (VIEW.x - 6, VIEW.y - 6, VW + 12, VH + 12), 3)
        self.frame = frame

    def _build_bg_procedural(self):
        bg = pygame.Surface((VW, VH))
        for y in range(VH):
            if y < HORIZON:
                f = y / HORIZON
                c = (int(10 + 26 * f), int(10 + 20 * f), int(16 + 12 * f))
            else:
                f = (y - HORIZON) / (VH - HORIZON)
                c = (int(34 - 20 * f), int(30 - 18 * f), int(26 - 16 * f))
            pygame.draw.line(bg, c, (0, y), (VW, y))

        x = 0
        while x < VW:
            w = random.randint(30, 80)
            h = random.randint(25, 95)
            pygame.draw.rect(bg, (14, 13, 16), (x, HORIZON - h, w, h))
            for _ in range(random.randint(0, 3)):
                wx = x + random.randint(4, max(5, w - 10))
                wy = HORIZON - random.randint(8, max(9, h - 4))
                pygame.draw.rect(bg, (24, 22, 18), (wx, wy, 5, 7))
            x += w + random.randint(0, 25)

        for _ in range(9):
            tx = random.randint(0, VW)
            th = random.randint(40, 90)
            pygame.draw.line(bg, (9, 9, 11), (tx, HORIZON), (tx, HORIZON - th), 4)

        for _ in range(500):
            gx = random.randint(0, VW)
            gy = random.randint(HORIZON, VH)
            v = random.randint(8, 30)
            pygame.draw.circle(bg, (v, v - 2, v - 4), (gx, gy), random.randint(1, 3))
        return bg

    def _apply_grade(self, surf):
        tint = pygame.Surface((VW, VH), pygame.SRCALPHA)
        tint.fill((10, 18, 26, 55))
        surf.blit(tint, (0, 0))

        vg = pygame.Surface((VW, VH), pygame.SRCALPHA)
        vg.fill((0, 0, 0, 150))
        R = int(math.hypot(VW, VH) * 0.42)
        clear = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        for r in range(R, 0, -3):
            a = int(150 * (1 - r / R) ** 0.6)
            pygame.draw.circle(clear, (0, 0, 0, a), (R, R), r)
        vg.blit(clear, (VW // 2 - R, VH // 2 - R), special_flags=pygame.BLEND_RGBA_SUB)
        surf.blit(vg, (0, 0))

    def _build_fence_procedural(self):
        fence = pygame.Surface((VW, VH), pygame.SRCALPHA)
        y1, y2 = FENCE_Y1, FENCE_Y2
        fh = y2 - y1
        sp = 18

        grid_surf = pygame.Surface((VW, fh), pygame.SRCALPHA)
        for i in range(-fh, VW + fh, sp):
            pygame.draw.line(grid_surf, (135, 140, 148, 150), (i, 0), (i + fh, fh), 2)
            pygame.draw.line(grid_surf, (135, 140, 148, 150), (i + fh, 0), (i, fh), 2)
        fence.blit(grid_surf, (0, y1))

        pygame.draw.rect(fence, (45, 46, 50, 255), (0, y1, VW, fh), 8)

        for y_pos in (y1, y1 + fh // 2, y2):
            pygame.draw.line(fence, (62, 64, 70, 255), (0, y_pos), (VW, y_pos), 6)
            pygame.draw.line(fence, (150, 154, 160, 160), (0, y_pos - 1), (VW, y_pos - 1), 1)

        for px in (int(VW * 0.27), int(VW * 0.52), int(VW * 0.74)):
            pygame.draw.rect(fence, (58, 60, 65, 255), (px - 5, y1, 10, fh))
            pygame.draw.rect(fence, (150, 154, 160, 140), (px - 5, y1, 2, fh))
            for by in range(y1 + 12, y2, 45):
                pygame.draw.circle(fence, (20, 20, 22, 255), (px, by), 3)

        warn = pygame.Rect(int(VW * 0.74) + 10, y1 + 10, 46, 28)
        pygame.draw.rect(fence, (180, 150, 20, 230), warn, border_radius=3)
        pygame.draw.rect(fence, (40, 32, 6, 230), warn, 2, border_radius=3)
        return fence

    def rebuild_fence_surface(self):
        fence = self.fence_base.copy()
        y1, y2 = FENCE_Y1, FENCE_Y2
        fh = y2 - y1
        cy = (y1 + y2) // 2
        for hole in self.fence_holes:
            x1 = int(VW * (0.10 + 0.80 * hole["x1"]))      # misma proyección que usa el zombi
            x2 = int(VW * (0.10 + 0.80 * hole["x2"]))
            gap_h = fh * hole["open"]
            if gap_h > 1:
                hy1, hy2 = int(cy - gap_h / 2), int(cy + gap_h / 2)
                rect = pygame.Rect(x1, hy1, max(1, x2 - x1), max(1, hy2 - hy1))
                fence.fill((0, 0, 0, 0), rect, special_flags=pygame.BLEND_RGBA_MIN)
                if hole["open"] > 0.12:
                    rng = random.Random(x1 * 1000 + 17)
                    for _ in range(6):
                        wx = rng.randint(x1, max(x1, x2))
                        wy = rng.choice([hy1, hy2])
                        ang = rng.uniform(-0.6, 0.6) + (1.57 if wy == hy2 else -1.57)
                        L = rng.uniform(6, 16) * hole["open"]
                        pygame.draw.line(fence, (150, 154, 160, 210), (wx, wy),
                                         (wx + math.cos(ang) * L, wy + math.sin(ang) * L), 1)
        self.fence = fence

    def check_fence_hole(self, nx):
        return any(h["x1"] <= nx <= h["x2"] and h["open"] > 0.2 for h in self.fence_holes)

    def create_fence_hole(self, nx, width=0.08):
        half = (width / 0.80) / 2                  # el ancho está en pantalla; nx se proyecta con 0.80
        x1, x2 = max(0.0, nx - half), min(1.0, nx + half)
        self.fence_holes.append({"x1": x1, "x2": x2, "open": 0.25, "grow": True})   # se abre de golpe
        self.rebuild_fence_surface()

    def fence_impact(self, z):
        """Punto de la valla donde golpea el zombi."""
        cx, fy, h = z.geom()
        return cx, min(max(fy - h * 0.55, FENCE_Y1 + 20), FENCE_Y2 - 20)

    def add_debris(self, x, y, n, y_spread=0, up=False):
        for _ in range(n):
            a = random.uniform(-3.4, -0.2) if up else random.uniform(0, math.tau)
            v = random.uniform(70, 250)
            self.debris.append([x, y + random.uniform(-y_spread, y_spread), math.cos(a) * v,
                                math.sin(a) * v - (0 if up else 80), random.uniform(0.35, 0.9),
                                random.randint(2, 5), random.randint(0, 1)])

    def fence_hit(self, z):
        """Golpe que aún no rompe la valla: sonido, chispas y grietas (se dibujan en draw_fence_cracks)."""
        ix, iy = self.fence_impact(z)
        self.play("hit", vol=0.6)
        self.add_debris(ix, iy, 6, up=True)

    def break_fence(self, z):
        """Último golpe: la valla se rompe, salen escombros y se abre el hueco."""
        ix, iy = self.fence_impact(z)
        self.play("hit", vol=0.7)
        self.play("fence_break")
        self.create_fence_hole(z.nx, width=0.12 if z.is_brute else 0.07)
        self.add_debris(ix, iy, 28, y_spread=(FENCE_Y2 - FENCE_Y1) * 0.35)
        self.shake_t = 0.22

    def draw_fence_cracks(self, s, z):
        """Grietas, abolladura y alambres doblados; crecen según el avance (golpes hechos / necesarios)."""
        ix, iy = self.fence_impact(z)
        frac = z.break_hits_done / z.break_hits_needed   # 0.25, 0.5, 0.75 (normal) · 0.5 (bruto)
        pulse = z.fence_shake / 0.3                      # 1.0 justo al golpear, baja a 0
        ix += random.uniform(-3, 3) * pulse
        iy += random.uniform(-3, 3) * pulse
        rng = random.Random(z.crack_seed)

        rad = int(12 + 26 * frac)
        dent = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
        for rr in range(rad, 0, -3):
            pygame.draw.circle(dent, (0, 0, 0, int(110 * (1 - rr / rad) + 15)), (rad, rad), rr)
        pygame.draw.circle(dent, (190, 195, 205, 120), (rad, rad), rad, 2)
        s.blit(dent, (int(ix - rad), int(iy - rad)))

        for _ in range(3 + int(10 * frac)):
            ang = rng.uniform(0, math.tau)
            length = rng.uniform(0.5, 1.0) * (18 + 50 * frac)
            pts, x, y = [(ix, iy)], ix, iy
            for _seg in range(3):
                ang += rng.uniform(-0.5, 0.5)
                x += math.cos(ang) * length / 3
                y += math.sin(ang) * length / 3
                pts.append((x, y))
            pygame.draw.lines(s, (18, 18, 20), False, pts, 3)
            pygame.draw.lines(s, (200, 205, 212), False, pts, 1)

        if frac >= 0.5:                                  # alambres reventados que sobresalen
            for _ in range(6):
                ang = rng.uniform(0, math.tau)
                r1, r2 = rng.uniform(8, 14), rng.uniform(22, 38)
                p1 = (ix + math.cos(ang) * r1, iy + math.sin(ang) * r1)
                p2 = (ix + math.cos(ang + 0.5) * r2, iy + math.sin(ang + 0.5) * r2)
                pygame.draw.line(s, (150, 154, 160), p1, p2, 2)

        if pulse > 0.5:                                  # destello del impacto
            pygame.draw.circle(s, (255, 235, 190), (int(ix), int(iy)), int(8 + 16 * pulse), 2)

    def damage_player(self, amount):
        """El escudo absorbe el daño primero; lo que sobra pasa a la salud."""
        if self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
            self.shield_fl = 0.35
            if amount <= 0:
                self.play("shield_hit")
                return
        self.hp -= amount
        self.hurt_fl = 0.50
        self.play("hurt")

    def roll_drop(self):
        tipos, pesos = zip(*DROP_WEIGHTS)
        return random.choices(tipos, weights=pesos, k=1)[0]

    def build_sounds(self):
        self.volume = load_volume()          # volumen general (0.0 - 1.0)
        self.snd = load_prerendered_sounds() if IS_WEB else None   # web: sonidos ya generados (carga rápida)
        if not self.snd:
            self.snd = sound_recipes()       # PC: se sintetizan al iniciar
        self.vol_base = {}                   # volumen propio de cada sonido (sin el volumen general)
        for v in self.snd.values():
            for snd in (v if isinstance(v, list) else [v]):
                if snd:
                    self.vol_base[id(snd)] = snd.get_volume()
        self.apply_volume()

    def play(self, name, vol=None):
        snd = self.snd.get(name)
        if isinstance(snd, list):
            snd = random.choice(snd)
        if snd:
            if vol is not None:
                self.vol_base[id(snd)] = vol
            snd.set_volume(self.vol_base.get(id(snd), 1.0) * self.volume)
            snd.play()

    def apply_volume(self):
        """Aplica el volumen general a todos los sonidos (también al viento que suena en bucle)."""
        for v in self.snd.values():
            for snd in (v if isinstance(v, list) else [v]):
                if snd:
                    snd.set_volume(self.vol_base.get(id(snd), 1.0) * self.volume)

    def adjust_volume(self, delta, wrap=False):
        pasos = round(self.volume * 10) + round(delta * 10)
        if wrap and pasos > 10:
            pasos = 0
        self.volume = max(0, min(10, pasos)) / 10
        self.apply_volume()
        save_volume(self.volume)
        self.play("click")                   # se oye el nuevo nivel

    def volume_label(self):
        return "VOLUMEN  < %d%% >" % round(self.volume * 100)

    def reset(self):
        self.hp = 100.0
        self.shield = 0.0            # el escudo empieza vacío
        self.shield_fl = 0.0
        self.shake_t = 0.0
        self.debris = []
        self.max_ammo = 9
        self.ammo = 9
        self.heavy_ammo = 0
        self.score = 0
        self.kills = 0
        self.wave = 1
        self.score_saved = False

        cfg = DIFFICULTIES[self.difficulty]
        self.wave_total_zombies = int(5 * cfg["count"])
        self.wave_spawned = 0
        self.wave_killed = 0
        self.wave_pause_t = 0.0
        self.grenade_target = self.pick_grenade_target()

        self.zombies = []
        self.parts = []
        self.drops = []
        self.fence_holes = []
        self.fence_repair_charges = 0
        self.spawn_t = 1.0
        self.cool = 0.0
        self.reload_t = 0.0
        self.reload_total = RELOAD_AUTO
        self.grenades = 0
        self.grenade_fx = None
        self.boom_t = 0.0
        self.recoil = 0.0
        self.flash = 0.0
        self.hurt_fl = 0.0
        self.groan_t = 3.0
        self.msg = ""
        self.msg_t = 0.0
        if hasattr(self, 'fence'):
            self.rebuild_fence_surface()

    def start_new(self):
        self.reset()
        self.started = True
        self.state = "play"
        pygame.mouse.set_visible(False)

    def mouse_view(self):
        mx, my = self.mouse_pos()
        return (max(0, min(VW, mx - VIEW.x)), max(0, min(VH, my - VIEW.y)))

    def fire(self):
        if self.state != "play" or self.reload_t > 0 or self.cool > 0 or self.wave_pause_t > 0:
            return
        if self.ammo <= 0:
            self.play("click")
            self.start_reload()
            return

        px, py = self.mouse_view()

        for drop in self.drops[:]:
            if drop.hit_test(px, py):
                self.drops.remove(drop)
                self.play("powerup")
                if drop.type == "heavy_ammo":
                    self.heavy_ammo += 9
                    self.ammo = self.max_ammo
                    self.reload_t = 0.0
                    self.show("¡CARGADOR LLENO + BALAS PESADAS!")
                elif drop.type == "health":
                    self.hp = min(100.0, self.hp + 35)
                    self.show("¡SALUD RESTAURADA!")
                elif drop.type == "shield":
                    self.shield = min(MAX_SHIELD, self.shield + SHIELD_PER_BOX)
                    self.show("¡ESCUDO AL MÁXIMO!" if self.shield >= MAX_SHIELD else "¡ESCUDO +%d!" % SHIELD_PER_BOX)
                elif drop.type == "grenade":
                    self.grenades += 1
                    self.show("¡GRANADA! PRESIONA F")
                else:
                    self.fence_repair_charges += 1
                    self.show("¡REPARANDO LA VALLA...!" if self.fence_holes
                              else "¡REFUERZO DE VALLA EN RESERVA!")
                return

        self.ammo -= 1
        is_heavy = self.heavy_ammo > 0
        if is_heavy:
            self.heavy_ammo -= 1
            self.play("heavy_shot")
            self.cool = 0.30
            self.recoil = 1.6
            self.flash = 0.12
        else:
            self.play("shot")
            self.cool = 0.42
            self.recoil = 1.0
            self.flash = 0.08

        for z in sorted(self.zombies, key=lambda q: q.z):
            part = z.hit_test(px, py)
            if part:
                if part == "head":
                    dmg = 7 if is_heavy else 4
                    self.show("¡HEADSHOT!")
                elif part == "stomach":
                    dmg = 4 if is_heavy else 2
                    z.flinch_t = 0.35
                elif part == "arm":
                    dmg = 3 if is_heavy else 1.5
                    z.flinch_t = 0.35
                elif part == "leg":
                    dmg = 3 if is_heavy else 1.5
                    z.stumble_t = 1.8
                    self.show("¡TROPIEZO!")

                z.hp -= dmg
                z.hit_flash = 0.12
                z.add_wound(part, px, py)
                self.score += 10
                self.play("hit")

                cx, fy, h = z.geom()
                bx, by = (cx, fy - h * 0.86) if part == "head" else (px, py)

                for _ in range(24 if is_heavy else 12):
                    a = random.uniform(0, 6.28)
                    v = random.uniform(50, 240)
                    self.parts.append([bx, by, math.cos(a) * v, math.sin(a) * v - 60, random.uniform(0.3, 0.7)])

                if z.hp <= 0:
                    self.kills += 1
                    self.wave_killed += 1
                    base_pts = 120 if z.is_brute else 50
                    self.score += base_pts + (35 if part == "head" else 0)
                    self.play("die")

                    if self.kills % 4 == 0 or random.random() < 0.22:
                        self.drops.append(DropItem(cx, fy - h * 0.5, self.roll_drop()))
                    self.maybe_grenade_drop(cx, fy - h * 0.5)
                    self.check_wave_complete()
                break

        if self.ammo == 0:
            self.start_reload()

    def trigger_win(self):
        self.state = "win"
        if not self.score_saved:
            save_high_score(self.score, self.player_name, self.difficulty)
            self.score_saved = True
        if self.difficulty == "dificil":
            self.beast_unlocked = True
        pygame.mouse.set_visible(True)

    def start_reload(self, manual=False):
        """Recarga automática (sin balas): 1.5 s. Recarga manual (tecla R): 1.0 s."""
        if self.reload_t <= 0 and self.ammo < self.max_ammo:
            self.reload_total = RELOAD_MANUAL if manual else RELOAD_AUTO
            self.reload_t = self.reload_total
            self.play("reload")

    def check_wave_complete(self):
        if self.wave_killed >= self.wave_total_zombies and self.state == "play" and self.wave_pause_t <= 0:
            if self.wave >= MAX_WAVES:
                self.trigger_win()
            else:
                self.start_wave_pause()

    # ---------- granadas ----------
    def pick_grenade_target(self):
        """Elige en qué baja de la oleada cae la caja de granada (entre el 30 % y el 80 % de la oleada)."""
        if random.random() >= GRENADE_CHANCE_PER_WAVE:
            return None
        a = max(1, int(self.wave_total_zombies * 0.3))
        b = max(a, int(self.wave_total_zombies * 0.8))
        return random.randint(a, b)

    def maybe_grenade_drop(self, x, y):
        """Como mucho UNA caja de granada por oleada."""
        if self.grenade_target is not None and self.wave_killed >= self.grenade_target:
            self.drops.append(DropItem(x, y, "grenade"))
            self.grenade_target = None

    def throw_grenade(self):
        if self.state != "play" or self.grenade_fx or self.wave_pause_t > 0:
            return
        if self.grenades <= 0:
            self.show("SIN GRANADAS")
            self.play("click")
            return
        if not any(z.alive for z in self.zombies):
            self.show("NO HAY ENEMIGOS")
            return
        self.grenades -= 1
        self.grenade_fx = {"t": 0.0, "dur": 0.55}        # vuelo de 0.55 s y luego explota
        self.play("click")

    def explode_grenade(self):
        """Elimina a todos los zombis que hay en pantalla en ese momento."""
        victims = [z for z in self.zombies if z.alive]
        self.play("boom")
        self.boom_t = 0.6
        self.shake_t = 0.5
        last = None
        for z in victims:
            z.hp = 0
            z.hit_flash = 0.3
            cx, fy, h = z.geom()
            self.kills += 1
            self.wave_killed += 1
            self.score += 120 if z.is_brute else 50
            for _ in range(14):
                a = random.uniform(0, 6.28)
                v = random.uniform(60, 260)
                self.parts.append([cx, fy - h * 0.5, math.cos(a) * v, math.sin(a) * v - 80, random.uniform(0.3, 0.8)])
            last = (cx, fy - h * 0.5)
        self.add_debris(VW * 0.5, VH * 0.5, 40, y_spread=60)
        if victims:
            self.play("die")
            self.show("¡BOOM!  x%d" % len(victims))
            self.maybe_grenade_drop(*last)
        self.check_wave_complete()

    def draw_grenade(self, s):
        fx = self.grenade_fx
        if not fx:
            return
        p = min(1.0, fx["t"] / fx["dur"])
        sx, sy, tx, ty = VW - 120, VH - 10, VW * 0.5, VH * 0.5
        x = sx + (tx - sx) * p
        y = sy + (ty - sy) * p - math.sin(p * math.pi) * 140      # trayectoria en arco
        r = int(10 - 4 * p)
        pygame.draw.circle(s, (45, 65, 38), (int(x), int(y)), r)
        pygame.draw.circle(s, (95, 125, 75), (int(x - r * 0.3), int(y - r * 0.3)), max(2, r // 3))
        pygame.draw.rect(s, (130, 130, 135), (int(x) - 2, int(y) - r - 3, 4, 4))

    def start_wave_pause(self):
        self.wave_pause_t = 5.0
        self.show("¡OLEADA %d COMPLETADA!" % self.wave)

    def show(self, text):
        self.msg, self.msg_t = text, 1.5

    def update(self, dt):
        if self.state != "play":
            return

        self.cool = max(0.0, self.cool - dt)
        self.recoil = max(0.0, self.recoil - dt * 4)
        self.flash = max(0.0, self.flash - dt)
        self.hurt_fl = max(0.0, self.hurt_fl - dt)
        self.shield_fl = max(0.0, self.shield_fl - dt)
        self.shake_t = max(0.0, self.shake_t - dt)
        self.msg_t = max(0.0, self.msg_t - dt)

        if self.reload_t > 0:
            self.reload_t -= dt
            if self.reload_t <= 0:
                self.ammo = self.max_ammo

        self.boom_t = max(0.0, self.boom_t - dt)
        if self.grenade_fx:
            self.grenade_fx["t"] += dt
            if self.grenade_fx["t"] >= self.grenade_fx["dur"]:
                self.grenade_fx = None
                self.explode_grenade()

        if self.wave_pause_t > 0:
            self.wave_pause_t -= dt
            if self.wave_pause_t <= 0:
                self.wave += 1
                self.wave_spawned = 0
                self.wave_killed = 0
                cfg = DIFFICULTIES[self.difficulty]
                self.wave_total_zombies = int((5 + self.wave * 3) * cfg["count"])
                self.grenade_target = self.pick_grenade_target()
                self.show("¡OLEADA %d!" % self.wave)
        else:
            if self.wave_spawned < self.wave_total_zombies:
                self.spawn_t -= dt
                if self.spawn_t <= 0:
                    cfg = DIFFICULTIES[self.difficulty]
                    self.spawn_t = max(0.4, 2.2 - self.wave * 0.18) * random.uniform(0.7, 1.2)
                    brute_chance = min(0.60, cfg["brute"] + self.wave * 0.04)
                    is_brute = random.random() < brute_chance
                    sp = 0.065 + self.wave * 0.008 + random.uniform(0, 0.02)
                    self.zombies.append(Zombie(sp, cfg, is_brute=is_brute))
                    self.wave_spawned += 1

        nearest = 1.0
        for z in self.zombies:
            z.update(dt, self)
            if z.alive:
                nearest = min(nearest, z.z)

        self.zombies = [z for z in self.zombies if not z.done]

        growing = False
        for h in self.fence_holes:                       # animación: el hueco se abre en 0.35 s
            if h.get("grow"):
                h["open"] = min(1.0, h["open"] + dt / 0.35)
                growing = True
                if h["open"] >= 1.0:
                    h.pop("grow")
        if growing:
            self.rebuild_fence_surface()

        hole = next((h for h in self.fence_holes if not h.get("grow")), None)
        if self.fence_repair_charges > 0 and hole:
            hole["open"] = max(0.0, hole["open"] - dt / FENCE_REPAIR_TIME)
            self.rebuild_fence_surface()
            if hole["open"] <= 0.0:
                self.fence_holes.remove(hole)
                self.fence_repair_charges -= 1
                self.rebuild_fence_surface()
                self.show("¡LA VALLA SE HA REPARADO!")

        for drop in self.drops:
            drop.update(dt)
        self.drops = [d for d in self.drops if not d.is_expired()]

        self.groan_t -= dt
        if self.groan_t <= 0:
            self.groan_t = random.uniform(2.5, 5.5)
            if any(z.alive for z in self.zombies):
                self.play("groan", vol=0.25 + 0.6 * (1 - nearest))

        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 500 * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]

        for d in self.debris:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 600 * dt
            d[4] -= dt
        self.debris = [d for d in self.debris if d[4] > 0]

        mx, my = self.mouse_view()
        k = min(1.0, dt * 9)
        self.light[0] += (mx - self.light[0]) * k
        self.light[1] += (my - self.light[1]) * k

        if self.hp <= 0:
            self.hp = 0
            if not self.score_saved:
                save_high_score(self.score, self.player_name, self.difficulty)
                self.score_saved = True
            self.state = "gameover"
            self.started = False
            pygame.mouse.set_visible(True)

    def draw_scene(self):
        scene = pygame.Surface((VW, VH))
        scene.blit(self.bg, (0, 0))

        eyes = []
        zombies_behind = [z for z in self.zombies if not z.crossed]
        zombies_front = [z for z in self.zombies if z.crossed]

        for z in sorted(zombies_behind, key=lambda q: -q.z):
            z.draw(scene, eyes)

        scene.blit(self.fence, (0, 0))
        for z in zombies_behind:
            if z.alive and z.state == "breaking_fence" and z.break_hits_done > 0:
                self.draw_fence_cracks(scene, z)

        for z in sorted(zombies_front, key=lambda q: -q.z):
            z.draw(scene, eyes)

        for drop in self.drops:
            drop.draw(scene, self.f_small)

        for p in self.parts:
            pygame.draw.circle(scene, (150, 15, 15), (int(p[0]), int(p[1])), 2)

        for d in self.debris:                            # escombros de la valla
            x, y = int(d[0]), int(d[1])
            if d[6] == 0:
                pygame.draw.circle(scene, (255, 220, 140), (x, y), 2)
            else:
                pygame.draw.line(scene, (170, 175, 182), (x, y), (x + int(d[2] * 0.03), y + int(d[3] * 0.03)),
                                 max(1, d[5] // 2))

        alpha = 225 if self.flash <= 0 else 110
        self.dark.fill((0, 0, 0, alpha))
        R = self.hole_r
        self.dark.blit(self.hole, (int(self.light[0] - R), int(self.light[1] - R)), special_flags=pygame.BLEND_RGBA_SUB)
        scene.blit(self.dark, (0, 0))

        for ex, ey, er, e_col in eyes:
            pygame.draw.circle(scene, e_col, (int(ex), int(ey)), er)

        self.draw_grenade(scene)
        mx, my = self.mouse_view()
        self.draw_weapon_and_hands(scene, mx, my)
        self.draw_crosshair(scene, mx, my)
        self.draw_hud(scene)

        if self.wave_pause_t > 0:
            overlay = pygame.Surface((VW, VH), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            scene.blit(overlay, (0, 0))

            t1 = self.f_title.render("¡OLEADA SUPERADA!", True, GOLD)
            t2 = self.f_mid.render("SIGUIENTE OLEADA EN: %.1f s" % self.wave_pause_t, True, (240, 240, 240))
            scene.blit(t1, (VW // 2 - t1.get_width() // 2, VH // 2 - 40))
            scene.blit(t2, (VW // 2 - t2.get_width() // 2, VH // 2 + 15))

        if self.hurt_fl > 0:
            ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
            alpha = int(220 * (self.hurt_fl / 0.50))
            ov.fill((210, 10, 10, min(255, alpha)))

            b_col = (140, 0, 0, min(255, alpha))
            b_col_light = (255, 60, 60, min(255, alpha))

            strokes = [
                [(VW * 0.15, VH * 0.1), (VW * 0.35, VH * 0.45), (VW * 0.50, VH * 0.2)],
                [(VW * 0.85, VH * 0.1), (VW * 0.65, VH * 0.45), (VW * 0.50, VH * 0.2)],
                [(VW * 0.25, VH * 0.88), (VW * 0.50, VH * 0.62), (VW * 0.75, VH * 0.88)],
            ]
            for st in strokes:
                pygame.draw.lines(ov, b_col, False, st, 14)
                pygame.draw.lines(ov, b_col_light, False, st, 6)

            scene.blit(ov, (0, 0))

        if self.shield_fl > 0:                           # destello celeste cuando el escudo absorbe un golpe
            ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
            ov.fill((70, 160, 255, int(110 * self.shield_fl / 0.35)))
            scene.blit(ov, (0, 0))

        if self.boom_t > 0:                              # destello de la explosión
            ov = pygame.Surface((VW, VH), pygame.SRCALPHA)
            ov.fill((255, 235, 190, int(210 * min(1.0, self.boom_t / 0.6))))
            scene.blit(ov, (0, 0))

        return scene

    def draw_crosshair(self, s, x, y):
        c = GOLD if self.heavy_ammo > 0 else (230, 25, 25)
        pygame.draw.circle(s, c, (x, y), 15, 1)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            pygame.draw.line(s, c, (x + dx * 6, y + dy * 6), (x + dx * 24, y + dy * 24), 2)

        if self.reload_t > 0:
            prog = 1.0 - (self.reload_t / self.reload_total)
            angle = int(360 * prog)
            arc_rect = pygame.Rect(x - 22, y - 22, 44, 44)
            pygame.draw.arc(s, CYAN, arc_rect, 0, math.radians(angle), 3)

    def draw_weapon_and_hands(self, s, mx, my):
        bx, by = VW - 120, VH + 25
        skin_col = (195, 140, 110)
        sleeve_col = (30, 45, 30)

        p_rel = 0.0
        if self.reload_t > 0:
            p_rel = 1.0 - (self.reload_t / self.reload_total)

        dip_y = math.sin(p_rel * math.pi) * 80 if self.reload_t > 0 else 0
        by += dip_y

        dx, dy = mx - bx, my - by
        d = math.hypot(dx, dy) or 1
        ux, uy = dx / d, dy / d
        px, py = -uy, ux

        kick = self.recoil * 22
        b = (bx - ux * kick, by - uy * kick)
        tip = (b[0] + ux * 220, b[1] + uy * 220)

        pygame.draw.line(s, (25, 25, 28), (b[0] + 50, b[1] + 80), (b[0] + ux * 35, b[1] + uy * 35), 42)
        pts = [(tip[0] + px * 6, tip[1] + py * 6), (tip[0] - px * 6, tip[1] - py * 6),
               (b[0] - px * 13, b[1] - py * 13), (b[0] + px * 13, b[1] + py * 13)]
        pygame.draw.polygon(s, (20, 20, 24), pts)

        r_hand = (b[0] + ux * 30, b[1] + uy * 30)
        pygame.draw.circle(s, skin_col, (int(r_hand[0]), int(r_hand[1])), 16)
        pygame.draw.line(s, sleeve_col, (int(r_hand[0]), int(r_hand[1])), (VW - 20, VH + 30), 28)

        if self.reload_t > 0:
            if p_rel < 0.33:
                sub_p = p_rel / 0.33
                l_hand = (b[0] + ux * 60 + px * 20, b[1] + uy * 60 + py * 20 + sub_p * 60)
                mag_y = b[1] + uy * 60 + sub_p * 110
                pygame.draw.rect(s, (15, 15, 15), (b[0] + ux * 60 - 5, mag_y, 10, 24))
            elif p_rel < 0.66:
                sub_p = (p_rel - 0.33) / 0.33
                mag_y = (VH + 50) - sub_p * (VH + 50 - (b[1] + uy * 60))
                l_hand = (b[0] + ux * 60 + px * 10, mag_y)
                pygame.draw.rect(s, GOLD, (l_hand[0] - 5, l_hand[1], 10, 24))
            else:
                sub_p = (p_rel - 0.66) / 0.34
                slide_off = math.sin(sub_p * math.pi) * 20
                l_hand = (b[0] + ux * 40 - ux * slide_off, b[1] + uy * 40 - uy * slide_off)

            pygame.draw.circle(s, skin_col, (int(l_hand[0]), int(l_hand[1])), 15)
            pygame.draw.line(s, sleeve_col, (int(l_hand[0]), int(l_hand[1])), (VW - 160, VH + 40), 24)

        else:
            l_hand = (b[0] + ux * 120, b[1] + uy * 120)
            pygame.draw.circle(s, skin_col, (int(l_hand[0]), int(l_hand[1])), 15)
            pygame.draw.line(s, sleeve_col, (int(l_hand[0]), int(l_hand[1])), (VW - 180, VH + 40), 24)

        if self.flash > 0:
            fl_col = (255, 230, 100) if self.heavy_ammo > 0 else (255, 180, 50)
            pts = []
            for i in range(10):
                a = i * math.pi / 5
                r = 42 if i % 2 == 0 else 16
                ang = math.atan2(uy, ux) + a
                pts.append((tip[0] + math.cos(ang) * r, tip[1] + math.sin(ang) * r))
            pygame.draw.polygon(s, fl_col, pts)

    def draw_hud(self, s):
        pygame.draw.rect(s, (30, 10, 8), (14, 12, 160, 16))
        pygame.draw.rect(s, RED, (14, 12, int(160 * self.hp / 100), 16))
        pygame.draw.rect(s, ORANGE, (14, 12, 160, 16), 1)
        s.blit(self.f_small.render("SALUD", True, ORANGE), (180, 12))

        pygame.draw.rect(s, (8, 22, 34), (14, 33, 160, 12))
        pygame.draw.rect(s, (215, 240, 255) if self.shield_fl > 0 else SKY,
                         (14, 33, int(160 * self.shield / MAX_SHIELD), 12))
        pygame.draw.rect(s, SKY, (14, 33, 160, 12), 1)
        s.blit(self.f_small.render("ESCUDO", True, SKY), (180, 32))

        t = self.f_mid.render("PUNTOS %d" % self.score, True, ORANGE)
        s.blit(t, (VW - t.get_width() - 14, 8))

        diff_name = DIFFICULTIES[self.difficulty]["name"]
        t2 = self.f_small.render("[%s] OLEADA %d/%d   BAJAS %d" % (diff_name, self.wave, MAX_WAVES, self.kills), True, (200, 140, 40))
        s.blit(t2, (VW - t2.get_width() - 14, 34))

        pygame.draw.polygon(s, (230, 130, 20), [(14, VH - 52), (14, VH - 12), (40, VH - 32)])
        for i in range(self.max_ammo):
            c = GOLD if (i < self.ammo and self.heavy_ammo > 0) else (ORANGE if i < self.ammo else (60, 35, 15))
            pygame.draw.circle(s, c, (54 + i * 14, VH - 32), 5)

        gx, gy = 190, VH - 32                            # granadas: icono + cantidad + tecla
        gcol = (255, 110, 40) if self.grenades > 0 else (80, 62, 50)
        pygame.draw.circle(s, gcol, (gx, gy + 2), 8)
        pygame.draw.rect(s, gcol, (gx - 2, gy - 10, 4, 5))
        s.blit(self.f_small.render("F x%d" % self.grenades, True, gcol), (gx + 14, gy - 7))

        if self.heavy_ammo > 0:
            ht = self.f_small.render("BALAS PESADAS: %d" % self.heavy_ammo, True, GOLD)
            s.blit(ht, (54, VH - 52))

        if self.reload_t > 0:
            t = self.f_small.render("RECARGANDO... (%.1fs)" % self.reload_total, True, CYAN)
            s.blit(t, (54, VH - 52 if self.heavy_ammo <= 0 else VH - 68))

        if self.msg_t > 0:
            t = self.f_big.render(self.msg, True, (240, 60, 40))
            s.blit(t, (VW // 2 - t.get_width() // 2, 60))

    def draw_frame(self):
        scr = self.screen
        scr.blit(self.frame, (0, 0))
        t = self.f_title.render("ZOMBIE HORDE", True, (240, 225, 200))
        scr.blit(t, (28, 18))
        t = self.f_title.render("BLACKOUT", True, ORANGE)
        scr.blit(t, (WIN_W - t.get_width() - 30, 52))

    def draw_high_scores(self, x, y):
        """Dibuja el panel de mejores puntajes segregado por dificultad."""
        scores = load_high_scores()
        box_w, box_h = 310, 380
        box_rect = pygame.Rect(x, y, box_w, box_h)

        pygame.draw.rect(self.screen, (22, 14, 12), box_rect, border_radius=8)
        pygame.draw.rect(self.screen, (110, 60, 20), box_rect, 2, border_radius=8)

        title = self.f_mid.render("MEJORES PUNTAJES", True, GOLD)
        self.screen.blit(title, (x + 12, y + 10))

        # Pestañas de filtro por dificultad
        tabs = [
            ("todos", "TODOS"),
            ("facil", "FÁCIL"),
            ("medio", "MEDIO"),
            ("dificil", "DIFÍCIL"),
            ("bestia", "BESTIA"),
        ]

        self.score_tab_rects = []
        tab_x = x + 10
        tab_y = y + 36
        tab_w = 55
        tab_h = 22

        mpos = self.mouse_pos()

        for key, label in tabs:
            r = pygame.Rect(tab_x, tab_y, tab_w, tab_h)
            self.score_tab_rects.append((key, r))
            is_sel = (self.score_tab == key)
            is_hover = r.collidepoint(mpos)

            bg_col = (140, 70, 15) if is_sel else ((70, 35, 12) if is_hover else (35, 20, 15))
            border_col = GOLD if is_sel else (100, 50, 20)
            txt_col = GOLD if is_sel else ((220, 220, 220) if is_hover else (150, 150, 150))

            pygame.draw.rect(self.screen, bg_col, r, border_radius=4)
            pygame.draw.rect(self.screen, border_col, r, 1, border_radius=4)

            t_lbl = self.f_small.render(label, True, txt_col)
            self.screen.blit(t_lbl, (r.centerx - t_lbl.get_width() // 2, r.centery - t_lbl.get_height() // 2))

            tab_x += tab_w + 3

        pygame.draw.line(self.screen, (90, 45, 18), (x + 10, y + 64), (x + box_w - 10, y + 64), 1)

        content_y = y + 70

        if not scores:
            no_s = self.f_small.render("Sin registros aún", True, (160, 160, 160))
            self.screen.blit(no_s, (x + 12, content_y))
            return

        if self.score_tab == "todos":
            curr_y = content_y
            for diff_key in ["facil", "medio", "dificil", "bestia"]:
                diff_cfg = DIFFICULTIES[diff_key]
                d_name = diff_cfg["name"]

                h_lbl = self.f_small.render(f"• {d_name}", True, CYAN if diff_key == "bestia" else GOLD)
                self.screen.blit(h_lbl, (x + 12, curr_y))
                curr_y += 18

                filtered = [s for s in scores if s.get("difficulty", "medio") == diff_key][:2]
                if not filtered:
                    no_e = self.f_small.render("  Sin registros", True, (120, 120, 120))
                    self.screen.blit(no_e, (x + 12, curr_y))
                    curr_y += 20
                else:
                    for idx, entry in enumerate(filtered):
                        name = (entry.get("name") or "???")[:12]
                        pts = f"{entry['score']} pts"
                        row_txt = self.f_small.render(f"  #{idx+1} {name}", True, (230, 230, 230))
                        pts_txt = self.f_small.render(pts, True, ORANGE)
                        self.screen.blit(row_txt, (x + 12, curr_y))
                        self.screen.blit(pts_txt, (x + box_w - pts_txt.get_width() - 15, curr_y))
                        curr_y += 18
                curr_y += 4
        else:
            diff_cfg = DIFFICULTIES[self.score_tab]
            d_name = diff_cfg["name"]

            h_lbl = self.f_mid.render(f"Dificultad: {d_name}", True, GOLD)
            self.screen.blit(h_lbl, (x + 12, content_y))
            curr_y = content_y + 26

            filtered = [s for s in scores if s.get("difficulty", "medio") == self.score_tab][:5]
            if not filtered:
                no_e = self.f_small.render("Sin registros en esta dificultad", True, (140, 140, 140))
                self.screen.blit(no_e, (x + 12, curr_y))
            else:
                for idx, entry in enumerate(filtered):
                    col = GOLD if idx == 0 else ((230, 230, 230) if idx < 3 else (160, 160, 160))
                    name = (entry.get("name") or "???")[:12]
                    pts = f"{entry['score']} pts"
                    dt_str = entry.get("date", "")

                    t_line = self.f_small.render(f"#{idx+1} {name}", True, col)
                    t_pts = self.f_small.render(pts, True, col)
                    t_dt = self.f_small.render(dt_str, True, (140, 140, 140))

                    self.screen.blit(t_line, (x + 12, curr_y))
                    self.screen.blit(t_pts, (x + box_w - t_pts.get_width() - 15, curr_y))
                    self.screen.blit(t_dt, (x + 12, curr_y + 16))
                    curr_y += 38

    def draw_name_entry(self):
        """Pantalla inicial: pide el nombre del jugador antes de entrar al menú."""
        veil = pygame.Surface((VW, VH), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 230))
        self.screen.blit(veil, VIEW.topleft)

        t = self.f_title.render("ZOMBIE BLACKOUT", True, ORANGE)
        self.screen.blit(t, (VIEW.x + 30, VIEW.y + 35))

        sub = self.f_mid.render("¿Cómo te llamas, superviviente?", True, (220, 200, 170))
        self.screen.blit(sub, (VIEW.x + 30, VIEW.y + 90))

        box = pygame.Rect(VIEW.x + 30, VIEW.y + 130, 320, 50)
        pygame.draw.rect(self.screen, (30, 20, 15), box, border_radius=6)
        pygame.draw.rect(self.screen, ORANGE, box, 2, border_radius=6)

        cursor_on = (pygame.time.get_ticks() // 450) % 2 == 0
        shown = self.name_input + ("_" if cursor_on else " ")
        txt = self.f_big.render(shown, True, (255, 235, 200))
        self.screen.blit(txt, (box.x + 14, box.y + box.h // 2 - txt.get_height() // 2))

        hint1 = self.f_small.render("Escribe tu nombre y presiona ENTER", True, (190, 170, 140))
        hint2 = self.f_small.render("(Máximo 14 caracteres)", True, (150, 135, 110))
        self.screen.blit(hint1, (VIEW.x + 30, VIEW.y + 192))
        self.screen.blit(hint2, (VIEW.x + 30, VIEW.y + 212))

        self.draw_high_scores(VIEW.x + 380, VIEW.y + 25)

    def get_menu_rects(self, overlay_type=None):
        n = MENU_N
        y0 = VIEW.y + 155
        step = 58
        return [pygame.Rect(VIEW.x + 30, y0 + i * step, 320, 48) for i in range(n)]

    def menu_buttons(self):
        labels = ["JUGAR", "DIFICULTAD: " + DIFFICULTIES[self.difficulty]["name"], self.volume_label(), "SALIR"][:MENU_N]
        if self.started and self.state == "menu":
            labels[0] = "CONTINUAR"
        return labels, self.get_menu_rects(None)

    def draw_menu(self, overlay_type=None):
        veil = pygame.Surface((VW, VH), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 220))
        self.screen.blit(veil, VIEW.topleft)

        if overlay_type == "win":
            t = self.f_title.render("¡SOBREVIVISTE A LA HORDA!", True, GOLD)
            sub = self.f_mid.render("Puntos: %d  |  Oleadas: %d" % (self.score, self.wave), True, (240, 240, 240))
            self.screen.blit(t, (VIEW.x + 30, VIEW.y + 30))
            self.screen.blit(sub, (VIEW.x + 30, VIEW.y + 80))

            if self.beast_unlocked:
                b_msg = self.f_small.render("¡DESBLOQUEADO: MODO BESTIA!", True, RED)
                self.screen.blit(b_msg, (VIEW.x + 30, VIEW.y + 110))

            labels = ["JUGAR DE NUEVO", "CAMBIAR DIFICULTAD", self.volume_label(), "SALIR"][:MENU_N]
            rects = self.get_menu_rects("win")

        elif overlay_type == "gameover":
            t = self.f_title.render("HAS SIDO DEVORADO", True, RED)
            sub = self.f_mid.render("Puntos: %d  |  Bajas: %d  |  Oleada: %d" % (self.score, self.kills, self.wave), True, ORANGE)
            self.screen.blit(t, (VIEW.x + 30, VIEW.y + 30))
            self.screen.blit(sub, (VIEW.x + 30, VIEW.y + 85))

            labels = ["REINTENTAR", "CAMBIAR DIFICULTAD", self.volume_label(), "SALIR"][:MENU_N]
            rects = self.get_menu_rects("gameover")

        else:
            t = self.f_title.render("ZOMBIE BLACKOUT", True, ORANGE)
            sub = self.f_mid.render("Derrota 10 oleadas para ganar.", True, (220, 200, 170))
            self.screen.blit(t, (VIEW.x + 30, VIEW.y + 30))
            self.screen.blit(sub, (VIEW.x + 30, VIEW.y + 85))
            who = self.f_small.render("Jugador: %s" % self.player_name, True, (180, 200, 220))
            self.screen.blit(who, (VIEW.x + 30, VIEW.y + 110))
            hint = self.f_small.render("R recargar   F granada   TAB menú", True, (150, 130, 110))
            self.screen.blit(hint, (VIEW.x + 30, VIEW.y + 125))
            if not IS_WEB:
                hint2 = self.f_small.render("F11 / Alt+Enter: pantalla completa", True, (150, 130, 110))
                self.screen.blit(hint2, (VIEW.x + 30, VIEW.y + 139))
            labels, rects = self.menu_buttons()

        # Dibujar la tabla de puntajes en el lado derecho del menú
        self.draw_high_scores(VIEW.x + 380, VIEW.y + 25)

        mpos = self.mouse_pos()
        for i, (lb, r) in enumerate(zip(labels, rects)):
            if r.collidepoint(mpos):
                self.menu_sel = i
            sel = (i == self.menu_sel)
            pygame.draw.rect(self.screen, (120, 30, 15) if sel else (50, 18, 10), r, border_radius=6)
            pygame.draw.rect(self.screen, ORANGE if sel else (110, 60, 25), r, 2, border_radius=6)
            tx = self.f_big.render(lb, True, (255, 235, 200) if sel else (200, 150, 90))
            dy = -4 if lb.startswith("VOLUMEN") else 0
            self.screen.blit(tx, (r.centerx - tx.get_width() // 2, r.centery - tx.get_height() // 2 + dy))
            if lb.startswith("VOLUMEN"):                     # barra del nivel de volumen
                pygame.draw.rect(self.screen, (60, 25, 12), (r.x + 12, r.bottom - 10, r.w - 24, 4))
                pygame.draw.rect(self.screen, ORANGE, (r.x + 12, r.bottom - 10, int((r.w - 24) * self.volume), 4))

    def cycle_difficulty(self):
        order = ["facil", "medio", "dificil"]
        if self.beast_unlocked:
            order.append("bestia")
        curr_i = order.index(self.difficulty) if self.difficulty in order else 0
        self.difficulty = order[(curr_i + 1) % len(order)]

    def draw(self):
        self.draw_frame()
        if self.state in ("play", "gameover", "win") or self.started:
            scene = self.draw_scene()
            ox = oy = 0
            if self.recoil > 0.6 or self.hurt_fl > 0 or self.shake_t > 0:
                ox, oy = random.randint(-4, 4), random.randint(-4, 4)
            self.screen.blit(scene, (VIEW.x + ox, VIEW.y + oy))
        else:
            self.screen.blit(self.bg, VIEW.topleft)

        if self.state == "name_entry":
            self.draw_name_entry()
        elif self.state == "menu":
            self.draw_menu()
        elif self.state == "gameover":
            self.draw_menu(overlay_type="gameover")
        elif self.state == "win":
            self.draw_menu(overlay_type="win")
        self.present()

    def activate_menu(self, idx):
        if self.state in ("gameover", "win"):
            if idx == 0:
                self.start_new()
            elif idx == 1:
                self.cycle_difficulty()
            elif idx == 2:
                self.adjust_volume(0.1, wrap=True)
            elif idx == 3:
                self.quit_game()
        else:
            labels, _ = self.menu_buttons()
            lb = labels[idx]
            if lb in ("JUGAR", "REINICIAR"):
                self.start_new()
            elif lb == "CONTINUAR":
                self.state = "play"
                pygame.mouse.set_visible(False)
            elif lb.startswith("DIFICULTAD"):
                self.cycle_difficulty()
            elif lb.startswith("VOLUMEN"):
                self.adjust_volume(0.1, wrap=True)
            elif lb == "SALIR":
                self.quit_game()

    def handle(self, e):
        if e.type == pygame.QUIT:
            self.quit_game()
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_F11 or (e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                                         and getattr(e, "mod", 0) & pygame.KMOD_ALT):
                self.toggle_fullscreen()
                return
            if e.key == pygame.K_ESCAPE and self.fullscreen:      # ESC sale de pantalla completa
                self.toggle_fullscreen()
                return
            if e.key == pygame.K_ESCAPE and not IS_WEB:
                self.quit_game()
            if e.key == pygame.K_TAB or (IS_WEB and e.key == pygame.K_ESCAPE):
                if self.state == "play":
                    self.state = "menu"
                    self.menu_sel = 0
                    pygame.mouse.set_visible(True)
                elif self.state == "menu" and self.started:
                    self.state = "play"
                    pygame.mouse.set_visible(False)
                return

            if self.state == "name_entry":
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    typed = self.name_input.strip()
                    self.player_name = typed if typed else "SUPERVIVIENTE"
                    self.state = "menu"
                elif e.key == pygame.K_BACKSPACE:
                    self.name_input = self.name_input[:-1]
                else:
                    ch = getattr(e, "unicode", "")
                    if ch and ch.isprintable() and len(self.name_input) < 14:
                        self.name_input += ch
                return

            if self.state == "play":
                if e.key == pygame.K_SPACE:
                    self.fire()
                elif e.key == pygame.K_r:
                    self.start_reload(manual=True)
                elif e.key == pygame.K_f:
                    self.throw_grenade()
            else:
                n = MENU_N
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.menu_sel = (self.menu_sel - 1) % n
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    self.menu_sel = (self.menu_sel + 1) % n
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.activate_menu(self.menu_sel)
                elif e.key in (pygame.K_LEFT, pygame.K_a) and self.menu_sel == VOL_IDX:
                    self.adjust_volume(-0.1)
                elif e.key in (pygame.K_RIGHT, pygame.K_d) and self.menu_sel == VOL_IDX:
                    self.adjust_volume(0.1)

        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = self.to_canvas(e.pos)                       # coordenadas del lienzo, aunque la ventana esté escalada
            if self.state == "play":
                self.fire()
            else:
                if hasattr(self, 'score_tab_rects'):
                    for key, r in self.score_tab_rects:
                        if r.collidepoint(pos):
                            self.score_tab = key
                            return

                if self.state != "name_entry":
                    overlay = self.state if self.state in ("win", "gameover") else None
                    for i, r in enumerate(self.get_menu_rects(overlay)):
                        if r.collidepoint(pos):
                            if i == VOL_IDX:                 # mitad izquierda baja, mitad derecha sube
                                self.adjust_volume(-0.1 if pos[0] < r.centerx else 0.1)
                            else:
                                self.activate_menu(i)
                            break

    async def run(self):
        if MIXER_OK and self.snd.get("wind"):
            self.snd["wind"].play(loops=-1)
        while True:
            dt = min(self.clock.tick(60) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle(e)
            if self.state == "play" and pygame.key.get_pressed()[pygame.K_SPACE]:
                self.fire()
            self.update(dt)
            self.draw()
            await asyncio.sleep(0)      # cede el control al navegador en cada fotograma


async def main():
    await Game().run()


if __name__ == "__main__":
    asyncio.run(main())