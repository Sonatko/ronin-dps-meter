# -*- coding: utf-8 -*-
"""
Трекер чисел урона + расчёт DPS.

Идея (из наблюдений за Ronin):
  - УРОН уплывает ВВЕРХ и живёт ~1-2с, потом исчезает.
  - HP врага СТАТИЧНО висит над баром (не движется вверх).
  - СТАН/множитель = мелкое число с запятой рядом (тут уже отфильтровано матчером по слою/величине).

Алгоритм:
  - каждый кадр получаем числа {value, x, y, h, layer}
  - связываем с активными треками: то же value, близко по X, Y уменьшился (вверх) или почти равен
  - трек, который за свою жизнь СДВИНУЛСЯ ВВЕРХ суммарно >= move_thresh, помечается как УРОН
  - когда трек исчезает (не виден N кадров) и он был "урон" и ещё не зачтён -> добавляем value в DPS-события
  - HP-числа: не уплывают вверх -> трек живёт долго на месте -> не зачитывается
  - AUTO-PAUSE: если N сек без нового урона -> бой на паузе, таймер замораживается
  - DPS = сумма value за скользящее окно / окно
"""
from __future__ import annotations
import threading
from dataclasses import dataclass
from typing import Literal


@dataclass
class Track:
    value: int
    x: float
    y: float
    h: float
    t_first: float
    t_last: float
    y_start: float
    layer: Literal["white", "red"] = "white"  # тип урона (обычный/крит)
    counted: bool = False
    rise: float = 0.0          # суммарный подъём вверх (px)


class DamageTracker:
    def __init__(self, dps_window: float = 5.0,
                 match_x_frac: float = 1.2,     # допуск по X в долях высоты числа
                 rise_frac: float = 0.25,       # порог "уплыл вверх" в долях высоты числа
                 forget_sec: float = 0.6,
                 min_damage: int = 10,          # отсев мусорных мелких чисел (обрезки/стан)
                 max_damage: int = 999999999,
                 max_lifetime: float = 1.8,     # урон живёт ~1-2с; дольше = HP/UI (статика) -> НЕ урон
                 combat_timeout: float = 3.0) -> None:  # сек без урона до паузы боя
        self.dps_window = dps_window
        self.match_x_frac = match_x_frac
        self.rise_frac = rise_frac
        self.forget_sec = forget_sec
        self.min_damage = min_damage
        self.max_damage = max_damage
        self.max_lifetime = max_lifetime
        self.combat_timeout = combat_timeout
        self.tracks: list[Track] = []
        self.events: list[tuple[float, int, Literal["white", "red"]]] = []   # (время, урон, слой) — окно DPS
        self.hit_log: list[tuple[float, int, str]] = []   # ВСЕ засчитанные удары (не обрезается) — отладка/разбор
        self.total_session: int = 0
        # update() зовётся из потока-consumer, метрики читаются из UI-потока ->
        # один lock защищает self.events/tracks от "list changed during iteration".
        self._lock = threading.Lock()

        # AUTO-PAUSE: активное время боя (= ACTIVITY time как в WoW Details)
        self.combat_active_time: float = 0.0  # накопленное активное время (тикает только пока идёт урон)
        self.last_hit_time: float | None = None  # время последнего засчитанного урона
        self.combat_start_time: float | None = None  # время начала текущего сегмента боя
        # EFFECTIVE time (как в WoW Details): от ПЕРВОГО до ПОСЛЕДНЕГО удара,
        # включая простои внутри боя. effective_dps = total / effective_time.
        self.first_hit_time: float | None = None  # время самого первого засчитанного удара

        # Расширенные метрики
        self.peak_dps: float = 0.0
        self.max_hit: int = 0
        self.crit_total: int = 0  # суммарный крит-урон

    def update(self, numbers: list[dict], now: float) -> None:
        with self._lock:
            self._update_locked(numbers, now)

    def _update_locked(self, numbers: list[dict], now: float) -> None:
        # 1) сопоставление чисел с треками
        for num in numbers:
            v, x, y, h = num["value"], num["x"], num["y"], num["h"]
            layer = num.get("layer", "white")
            if v < self.min_damage or v > self.max_damage:
                continue   # мусор: обрезки/стан/слипания
            best, best_d = None, 1e9
            for tr in self.tracks:
                if tr.value != v:
                    continue
                dx = abs(x - tr.x)
                dy = tr.y - y               # >0 если поднялось вверх
                # допуск: близко по X, и Y не ниже прежнего сильно (урон уходит вверх)
                if dx <= h * self.match_x_frac and dy >= -h * 0.5:
                    d = dx + abs(dy)
                    if d < best_d:
                        best_d, best = d, tr
            if best is not None:
                rise = best.y - y
                if rise > 0:
                    best.rise += rise
                best.x, best.y, best.h, best.t_last = x, y, h, now
            else:
                self.tracks.append(Track(v, x, y, h, now, now, y, layer))

        # 2) истечение треков -> зачёт урона
        alive = []
        for tr in self.tracks:
            lifetime = tr.t_last - tr.t_first
            if lifetime > self.max_lifetime:
                # число висит слишком долго = HP/UI (твоё HP над персонажем), НЕ урон.
                # держим трек живым (чтобы повторно не создавался), но никогда не засчитываем.
                tr.counted = True
                alive.append(tr)
                continue
            if now - tr.t_last > self.forget_sec:
                # трек закрыт. УРОН, если: уплыл вверх ИЛИ прожил хотя бы 2 кадра
                # (короткое всплывающее число = удар), но НЕ слишком долго (см. выше).
                moved = tr.rise >= tr.h * self.rise_frac
                lived = lifetime >= 0.05
                if not tr.counted and (moved or lived):
                    self.events.append((tr.t_last, tr.value, tr.layer))
                    self.hit_log.append((tr.t_last, tr.value, tr.layer))
                    self.total_session += tr.value
                    if tr.layer == "red":
                        self.crit_total += tr.value
                    self.max_hit = max(self.max_hit, tr.value)
                    if self.first_hit_time is None:
                        self.first_hit_time = tr.t_last   # старт effective-таймера
                    self.last_hit_time = now  # засчитан урон -> обновить время боя
            else:
                alive.append(tr)
        self.tracks = alive

        # 3) AUTO-PAUSE: обновить активное время боя
        if self.combat_start_time is None:
            # боя ещё не было или он закончился после паузы
            if self.last_hit_time is not None and now - self.last_hit_time <= self.combat_timeout:
                self.combat_start_time = self.last_hit_time
        else:
            # бой идёт
            if self.last_hit_time is not None and now - self.last_hit_time > self.combat_timeout:
                # пауза: заморозить время по ПОСЛЕДНЕМУ удару (не now — иначе пауза попадёт в время боя)
                self.combat_active_time += self.last_hit_time - self.combat_start_time
                self.combat_start_time = None
            else:
                # бой продолжается
                pass

        # 4) чистка окна DPS
        cutoff = now - self.dps_window
        self.events = [(t, v, l) for (t, v, l) in self.events if t >= cutoff]

        # 5) обновить peak_dps (НЕ через self.dps() — lock уже захвачен, будет deadlock)
        current_dps = sum(v for _, v, _ in self.events) / self.dps_window if self.events else 0.0
        self.peak_dps = max(self.peak_dps, current_dps)

    def dps(self) -> float:
        """Текущий DPS (сумма урона за окно / окно)."""
        with self._lock:
            return sum(v for _, v, _ in self.events) / self.dps_window if self.events else 0.0

    def window_total(self) -> int:
        """Урон за последнее окно DPS."""
        with self._lock:
            return sum(v for _, v, _ in self.events)

    def hits(self) -> int:
        """Число ударов за окно DPS."""
        with self._lock:
            return len(self.events)

    def combat_time(self) -> float:
        """Активное время боя в секундах (без пауз)."""
        with self._lock:
            return self._combat_time_locked()

    def _combat_time_locked(self) -> float:
        result = self.combat_active_time
        if self.combat_start_time is not None and self.last_hit_time is not None:
            result += self.last_hit_time - self.combat_start_time
        return result

    def effective_time(self) -> float:
        """EFFECTIVE время боя (как WoW Details): от первого до последнего удара,
        ВКЛЮЧАЯ простои внутри боя. Это база для 'настоящего' DPS из логов."""
        with self._lock:
            if self.first_hit_time is None or self.last_hit_time is None:
                return 0.0
            return max(0.0, self.last_hit_time - self.first_hit_time)

    def effective_dps(self) -> float:
        """Effective DPS = total / полное_время_боя (как Details по умолчанию)."""
        with self._lock:
            if self.first_hit_time is None or self.last_hit_time is None:
                return 0.0
            t = self.last_hit_time - self.first_hit_time
            return self.total_session / t if t > 0 else 0.0

    def avg_dps(self) -> float:
        """ACTIVITY DPS = total / активное_время (только пока шёл урон, без простоев).
        В WoW Details это 'activity time' DPS — всегда >= effective."""
        with self._lock:
            ct = self._combat_time_locked()
            if ct > 0.0:
                return self.total_session / ct
            return 0.0

    # синоним для ясности (как actor:Tempo() в Details)
    def activity_dps(self) -> float:
        return self.avg_dps()

    def crit_rate(self) -> float:
        """Доля крит-урона от общего (по урону, не по числу ударов)."""
        with self._lock:
            if self.total_session > 0:
                return self.crit_total / self.total_session
            return 0.0

    def reset(self) -> None:
        """Сбросить все метрики (для кнопки Reset)."""
        with self._lock:
            self.tracks = []
            self.events = []
            self.total_session = 0
            self.combat_active_time = 0.0
            self.last_hit_time = None
            self.combat_start_time = None
            self.first_hit_time = None
            self.hit_log = []
            self.peak_dps = 0.0
            self.max_hit = 0
            self.crit_total = 0
