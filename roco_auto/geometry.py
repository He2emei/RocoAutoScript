from __future__ import annotations

from dataclasses import dataclass
from random import randint


@dataclass(frozen=True)
class Scaler:
    base_width: int
    base_height: int
    width: int
    height: int

    @property
    def sx(self) -> float:
        return self.width / self.base_width

    @property
    def sy(self) -> float:
        return self.height / self.base_height

    def point(self, point: tuple[float, float]) -> tuple[int, int]:
        x, y = point
        return round(x * self.sx), round(y * self.sy)

    def box(self, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        return round(x1 * self.sx), round(y1 * self.sy), round(x2 * self.sx), round(y2 * self.sy)

    def x(self, value: float) -> int:
        return round(value * self.sx)

    def y(self, value: float) -> int:
        return round(value * self.sy)


def random_near(point: tuple[int, int], radius: int = 4) -> tuple[int, int]:
    x, y = point
    return x + randint(-radius, radius), y + randint(-radius, radius)
