import time

class Cooldown:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._last: float = 0

    def is_ready(self) -> bool:
        return (time.time() - self._last) >= self.seconds

    def reset(self):
        self._last = time.time()

    def remaining(self) -> float:
        diff = self.seconds - (time.time() - self._last)
        return max(0.0, diff)

    def ready_then_reset(self) -> bool:
        if self.is_ready():
            self.reset()
            return True
        return False