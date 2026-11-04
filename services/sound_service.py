import pygame
import time
from threading import Lock

from config import SOUND_UNPAID, SOUND_SUCCESS, SOUND_ERROR, SOUND_DETECT


class SoundService:
    def __init__(self):
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._last_play_time = 0
        self._play_lock = Lock()
        self._min_play_interval = 1.0  # Minimum 1 detik antara suara
        self._init_mixer()
        self._load_sounds()
        self._min_interval = 1.0  # default 1 detik

    def _init_mixer(self):
        try:
            pygame.mixer.init()
            print("[SOUND] ✅ Mixer initialized.")
        except Exception as e:
            print(f"[SOUND] ❌ Mixer error: {e}")

    def _load_sounds(self):
        sound_files = {
            "unpaid": SOUND_UNPAID,
            # "success": SOUND_SUCCESS,
            # "error": SOUND_ERROR,
            "detect": SOUND_DETECT,
        }
        for key, path in sound_files.items():
            self._sounds[key] = self._load(path)

    def _load(self, path):
        try:
            return pygame.mixer.Sound(path)
        except Exception as e:
            print(f"[SOUND] Failed load {path}: {e}")
            return None

    def _can_play(self, interval=None):
        now = time.time()
        interval = interval or self._min_interval

        with self._play_lock:
            if now - self._last_play_time >= interval:
                self._last_play_time = now
                return True
            return False

    def _play(self, key, interval=None):
        if not self._can_play(interval):
            return

        sound = self._sounds.get(key)
        if sound:
            try:
                if pygame.mixer.get_busy():
                    pygame.mixer.stop()
                sound.play()
                print(f"[SOUND] Playing: {key}")
            except Exception as e:
                print(f"[SOUND] Error: {e}")

    def play_detect(self):
        self._play("detect", interval=5)

    def play_unpaid(self):
        self._play("unpaid")

    # def play_success(self):
    #     self._play("success")

    # def play_error(self):
    #     self._play("error")
