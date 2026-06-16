# -*- coding: utf-8 -*-
"""
Захват кадров окна эмулятора + frame-diff (пропуск неизменившихся кадров).

Универсально для любого эмулятора на ПК: ищем окно по подстроке заголовка
(BlueStacks/LDPlayer/Nox/MEmu), захватываем его клиентскую область.
"""
from __future__ import annotations
import numpy as np
import win32gui
import mss


def find_window(title_substr: str) -> tuple[int, tuple[int, int, int, int]] | tuple[None, None]:
    """Найти окно по подстроке заголовка. Вернуть (hwnd, (left, top, w, h)) клиентской области."""
    matches: list[int] = []

    def _cb(hwnd: int, _) -> None:
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            # игнорируем собственное окно оверлея, чтобы не захватить его вместо игры
            if t == "Ronin DPS":
                return
            if title_substr.lower() in t.lower():
                matches.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    if not matches:
        return None, None
    # предпочитаем крупное окно (игра), а не мелкое (вдруг что-то ещё совпало)
    matches.sort(key=lambda h: -(win32gui.GetClientRect(h)[2] * win32gui.GetClientRect(h)[3]))
    hwnd = matches[0]
    rect = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    return hwnd, (left, top, w, h)


def list_windows() -> list[str]:
    """Список заголовков видимых окон (для выбора пользователем)."""
    titles: list[str] = []

    def _cb(hwnd: int, _) -> None:
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if t.strip():
                titles.append(t)

    win32gui.EnumWindows(_cb, None)
    return titles


def list_windows_detailed() -> list[dict]:
    """Список видимых окон с размерами и hwnd — для выбора пользователем в UI.

    Возвращает [{'hwnd', 'title', 'w', 'h'}], отсортировано по площади (крупные = игра
    сверху). Мелкие окна (<300px) и собственный оверлей отфильтрованы.
    """
    # системные окна, которые точно не игра — прячем из списка
    _SYS = {"program manager", "nvidia geforce overlay", "интерфейс ввода windows",
            "параметры", "settings", "фотографии", "photos", "ronin dps meter",
            "default ime", "msctfime ui"}
    out: list[dict] = []

    def _cb(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        t = win32gui.GetWindowText(hwnd)
        if not t.strip() or t.lower() in _SYS:
            return
        try:
            r = win32gui.GetClientRect(hwnd)
            w, h = r[2] - r[0], r[3] - r[1]
        except Exception:
            return
        if w < 300 or h < 200:   # мелкое = не игра
            return
        out.append({"hwnd": hwnd, "title": t, "w": w, "h": h})

    win32gui.EnumWindows(_cb, None)
    out.sort(key=lambda d: -(d["w"] * d["h"]))
    return out


class WindowCapture:
    """Высокочастотный захват окна.

    DXcam (Desktop Duplication API, 240+fps) если доступен, иначе mss (60fps fallback).
    DXcam с target_fps непрерывно набивает ring-buffer в потоке — get_latest_frame()
    отдаёт свежайший кадр без задержки. Это ловит быстро-мелькающий урон.
    """

    def __init__(self, title_substr: str, target_fps: int = 60,
                 hwnd: int | None = None,
                 region: tuple[int, int, int, int] | None = None) -> None:
        if region is not None:
            # произвольная область экрана (рамка мышью) — не зависит от окна/эмулятора
            self.hwnd = None
            rect = region
        elif hwnd is not None:
            # окно выбрано пользователем явно (по hwnd) — надёжнее подстроки
            self.hwnd = hwnd
            r = win32gui.GetClientRect(hwnd)
            left, top = win32gui.ClientToScreen(hwnd, (0, 0))
            rect = (left, top, r[2] - r[0], r[3] - r[1])
        else:
            hwnd, rect = find_window(title_substr)
            self.hwnd = hwnd
        if rect is None:
            raise RuntimeError(f"Окно '{title_substr}' не найдено")
        self.left, self.top, self.width, self.height = rect
        self.backend = "mss"
        self._cam = None
        self._sct = None
        try:
            import dxcam
            self._cam = dxcam.create(output_color="BGR")
            region = (self.left, self.top, self.left + self.width, self.top + self.height)
            self._cam.start(region=region, target_fps=target_fps, video_mode=True)
            self.backend = "dxcam"
        except Exception:
            self._sct = mss.mss()

    def monitor(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    def grab(self) -> np.ndarray | None:
        """Свежайший кадр окна в BGR (или None если новый ещё не готов)."""
        if self.backend == "dxcam":
            frame = self._cam.get_latest_frame()   # блокирует до нового кадра
            return frame
        raw = np.array(self._sct.grab(self.monitor()))
        return raw[:, :, :3]

    def stop(self) -> None:
        if self.backend == "dxcam" and self._cam is not None:
            try:
                self._cam.stop()
            except Exception:
                pass
