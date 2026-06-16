# -*- coding: utf-8 -*-
"""
DPS-оверлей: красивое окошко поверх всех окон (always-on-top, перетаскиваемое, alpha~0.9).
Показывает: текущий DPS (крупно), пик, среднее, всего, крит%, макс удар, время боя, кол-во ударов, кнопка Reset.
Обновляется из главного потока через метод update_stats().
"""
from __future__ import annotations
import tkinter as tk
from typing import Callable


def select_region(preset: tuple[int, int, int, int] | None = None) -> tuple[int, int, int, int] | None:
    """Выбор области захвата РАМКОЙ МЫШЬЮ (как OBS region / Capture2Text).

    Затемняет весь экран, юзер протягивает прямоугольник по игровому полю.
    Возвращает (left, top, width, height) в экранных координатах или None если отменили.
    Не зависит от эмулятора/заголовка окна — работает у всех. Можно обвести только
    игровое поле без HUD-углов (тогда кнопки/уровень/золото не попадут в кадр).

    preset: показать прошлую рамку для подтверждения/переобводки (необязательно).
    """
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.30)            # полупрозрачное затемнение
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.config(cursor="cross")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    sw = root.winfo_screenwidth()
    canvas.create_text(sw // 2, 40, fill="#ff6b6b", font=("Segoe UI", 20, "bold"),
                       text="Обведите ИГРОВОЕ ПОЛЕ (без углов с кнопками). ЛКМ — тянуть, Esc — отмена")

    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                outline="#ff6b6b", width=3)

    def on_drag(e):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        x0, y0 = state["x0"], state["y0"]
        x1, y1 = e.x, e.y
        left, top = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w >= 50 and h >= 50:                # игнор случайного клика
            state["result"] = (left, top, w, h)
            root.destroy()

    def on_esc(_):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_esc)
    root.mainloop()
    return state["result"]


def choose_window(windows: list[dict], preselect_substr: str = "") -> dict | None:
    """Окно выбора игры: список окон (заголовок + размер), юзер кликает нужное.

    windows: [{'hwnd','title','w','h'}] из capture.list_windows_detailed().
    Возвращает выбранный dict или None если закрыли без выбора.
    Окна с preselect_substr в заголовке подсвечены и идут первыми.
    """
    if not windows:
        return None
    result: dict = {"choice": None}

    root = tk.Tk()
    root.title("Выбор окна игры")
    root.attributes("-topmost", True)
    root.configure(bg="#1a1a1a")
    root.geometry("460x420+200+150")

    tk.Label(root, text="Выберите окно игры (эмулятор):", fg="#dddddd", bg="#1a1a1a",
             font=("Segoe UI", 11, "bold")).pack(pady=(12, 4), padx=12, anchor="w")
    tk.Label(root, text="Обычно это самое большое окно эмулятора (BlueStacks/LDPlayer).",
             fg="#888888", bg="#1a1a1a", font=("Segoe UI", 8)).pack(padx=12, anchor="w")

    list_frame = tk.Frame(root, bg="#1a1a1a")
    list_frame.pack(fill="both", expand=True, padx=12, pady=8)
    sb = tk.Scrollbar(list_frame)
    sb.pack(side="right", fill="y")
    lb = tk.Listbox(list_frame, bg="#222222", fg="#dddddd", font=("Consolas", 10),
                    selectbackground="#ff6b6b", selectforeground="#1a1a1a",
                    yscrollcommand=sb.set, activestyle="none", border=0, highlightthickness=0)
    lb.pack(side="left", fill="both", expand=True)
    sb.config(command=lb.yview)

    for i, w in enumerate(windows):
        lb.insert("end", f"{w['title'][:40]:<40}  {w['w']}x{w['h']}")
        if preselect_substr and preselect_substr.lower() in w["title"].lower():
            lb.selection_set(i)
    if not lb.curselection():
        lb.selection_set(0)   # по умолчанию самое крупное

    def _ok() -> None:
        sel = lb.curselection()
        if sel:
            result["choice"] = windows[sel[0]]
        root.destroy()

    def _refresh() -> None:
        # перечитать список окон (вдруг игру открыли только что)
        from capture import list_windows_detailed
        nonlocal windows
        windows = list_windows_detailed()
        lb.delete(0, "end")
        for w in windows:
            lb.insert("end", f"{w['title'][:40]:<40}  {w['w']}x{w['h']}")
        if windows:
            lb.selection_set(0)

    btn_frame = tk.Frame(root, bg="#1a1a1a")
    btn_frame.pack(fill="x", padx=12, pady=(0, 12))
    tk.Button(btn_frame, text="Обновить список", fg="#dddddd", bg="#333333",
              font=("Segoe UI", 9), command=_refresh, border=0, padx=8, pady=4).pack(side="left")
    tk.Button(btn_frame, text="Выбрать", fg="#1a1a1a", bg="#ff6b6b",
              font=("Segoe UI", 9, "bold"), command=_ok, border=0, padx=12, pady=4).pack(side="right")
    lb.bind("<Double-Button-1>", lambda e: _ok())

    root.mainloop()
    return result["choice"]


class DpsOverlay:
    def __init__(self, window_sec: float = 5.0, on_reset: Callable[[], None] | None = None) -> None:
        self.root = tk.Tk()
        self.root.title("Ronin DPS Meter")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)
        self.root.overrideredirect(False)         # с рамкой — можно двигать
        self.root.configure(bg="#1a1a1a")
        self.root.geometry("340x400+40+40")

        self.window_sec = window_sec
        self._closed = False
        self._on_reset = on_reset or (lambda: None)

        # Тёмная тема с контрастным текстом
        bg_color = "#1a1a1a"
        fg_main = "#ff6b6b"      # крупный DPS — красный
        fg_label = "#888888"      # подписи
        fg_value = "#dddddd"      # значения метрик
        font_label = ("Segoe UI", 9)
        font_value = ("Consolas", 11, "bold")
        font_dps = ("Consolas", 48, "bold")

        # === Строка 1: крупный EFFECTIVE DPS (как WoW Details по умолчанию) ===
        # Главная цифра = total / полное_время_боя (effective). Растёт плавно.
        # Activity DPS (только время атаки) — в метриках рядом. Мгновенный — "Сейчас".
        header_frame = tk.Frame(self.root, bg=bg_color)
        header_frame.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(header_frame, text="DPS (за бой)", fg=fg_label, bg=bg_color,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        self._dps = tk.StringVar(value="0")   # effective_dps (главная цифра)
        tk.Label(self.root, textvariable=self._dps, fg=fg_main, bg=bg_color,
                 font=font_dps).pack()

        # === Разделитель ===
        tk.Frame(self.root, bg="#333333", height=1).pack(fill="x", padx=12, pady=6)

        # === Метрики (3 колонки) ===
        metrics_frame = tk.Frame(self.root, bg=bg_color)
        metrics_frame.pack(fill="both", expand=True, padx=12, pady=4)

        # Левая колонка
        left_col = tk.Frame(metrics_frame, bg=bg_color)
        left_col.pack(side="left", fill="both", expand=True)

        tk.Label(left_col, text="Пик", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w")
        self._peak = tk.StringVar(value="0")
        tk.Label(left_col, textvariable=self._peak, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        tk.Label(left_col, text="Сейчас", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w", pady=(4, 0))
        self._now = tk.StringVar(value="0")   # мгновенный DPS за окно (вторичный)
        tk.Label(left_col, textvariable=self._now, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        tk.Label(left_col, text="Всего", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w", pady=(4, 0))
        self._total = tk.StringVar(value="0")
        tk.Label(left_col, textvariable=self._total, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        # Средняя колонка
        mid_col = tk.Frame(metrics_frame, bg=bg_color)
        mid_col.pack(side="left", fill="both", expand=True, padx=(12, 0))

        tk.Label(mid_col, text="Крит%", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w")
        self._crit = tk.StringVar(value="0%")
        tk.Label(mid_col, textvariable=self._crit, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        tk.Label(mid_col, text="Макс", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w", pady=(4, 0))
        self._max = tk.StringVar(value="0")
        tk.Label(mid_col, textvariable=self._max, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        tk.Label(mid_col, text="Ударов", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w", pady=(4, 0))
        self._hits = tk.StringVar(value="0")
        tk.Label(mid_col, textvariable=self._hits, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        # Правая колонка
        right_col = tk.Frame(metrics_frame, bg=bg_color)
        right_col.pack(side="left", fill="both", expand=True, padx=(12, 0))

        tk.Label(right_col, text="Актив", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w")
        self._activity = tk.StringVar(value="0")   # activity DPS (без простоев)
        tk.Label(right_col, textvariable=self._activity, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        tk.Label(right_col, text="Бой (сек)", fg=fg_label, bg=bg_color, font=font_label).pack(anchor="w", pady=(4, 0))
        self._combat_time = tk.StringVar(value="0.0")
        tk.Label(right_col, textvariable=self._combat_time, fg=fg_value, bg=bg_color, font=font_value).pack(anchor="w")

        # === Кнопка Reset + подпись автора ===
        button_frame = tk.Frame(self.root, bg=bg_color)
        button_frame.pack(fill="x", padx=12, pady=(4, 6))
        reset_btn = tk.Button(button_frame, text="Сброс", fg="#1a1a1a", bg="#ff6b6b",
                              font=("Segoe UI", 9, "bold"),
                              command=self._on_reset_clicked,
                              padx=8, pady=4, border=0)
        reset_btn.pack(side="right")
        tk.Label(button_frame, text="by SONATO", fg="#666666", bg=bg_color,
                 font=("Segoe UI", 8)).pack(side="left", anchor="s")

        # подпись-ссылка внизу
        tk.Label(self.root, text="youtube.com/@sonato600  •  boosty.to/sonato600",
                 fg="#555555", bg=bg_color, font=("Segoe UI", 7)).pack(pady=(0, 6))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_reset_clicked(self) -> None:
        """Вызов калбэка сброса."""
        self._on_reset()

    def _on_close(self) -> None:
        self._closed = True
        self.root.destroy()

    @property
    def closed(self) -> bool:
        return self._closed

    def update_stats(self, dps: float, peak_dps: float, avg_dps: float,
                     window_total: int, hits: int, total: int,
                     crit_rate: float, max_hit: int, combat_time: float,
                     effective_dps: float = 0.0) -> None:
        """Обновить все метрики (схема DPS как в WoW Details).

        Args:
            dps: мгновенный DPS за окно 5с ("Сейчас")
            peak_dps: пиковый мгновенный DPS
            avg_dps: ACTIVITY DPS (total / время атаки, без простоев) — "Актив"
            effective_dps: EFFECTIVE DPS (total / полное время боя) — ГЛАВНАЯ цифра
            window_total: урон за окно
            hits: число ударов
            total: суммарный урон сессии
            crit_rate: доля крит-урона (0.0-1.0)
            max_hit: максимальный одиночный удар
            combat_time: активное время боя (сек)
        """
        if self._closed:
            return
        # Главная цифра = EFFECTIVE (как Details по умолчанию). Активити рядом.
        self._dps.set(f"{effective_dps:.0f}")
        self._activity.set(f"{avg_dps:.0f}")
        self._now.set(f"{dps:.0f}")
        self._peak.set(f"{peak_dps:.0f}")
        self._total.set(f"{total}")
        self._crit.set(f"{crit_rate*100:.1f}%")
        self._max.set(f"{max_hit}")
        self._hits.set(f"{hits}")
        self._combat_time.set(f"{combat_time:.1f}")

    def pump(self) -> None:
        """Прокрутить события Tk без блокировки (вызывать из главного цикла)."""
        if not self._closed:
            self.root.update_idletasks()
            self.root.update()
