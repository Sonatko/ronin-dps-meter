# -*- coding: utf-8 -*-
"""
Ronin DPS-метр — главный запуск.

Режимы:
  python main.py                      — реалтайм, окно по умолчанию из config
  python main.py --window "RONIN"     — указать окно эмулятора
  python main.py --video path.mp4     — прогон по видеозаписи (отладка/демо)
  python main.py --list-windows       — показать все окна и выйти

Зрение: template matching цифр урона -> трекинг уплывающих вверх -> DPS.
Не модифицирует игру, не лезет в память. Работает на CPU.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "core"))
from matcher import Matcher                      # noqa: E402  (CNN+template, белый+красный)
from tracker import DamageTracker               # noqa: E402

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULTS = {
    "window_title": "RONIN",
    "dps_window_sec": 5.0,
    "min_damage_height_frac": 0.006,
    "exclude_zones": [[0.0, 0.0, 1.0, 0.11], [0.0, 0.90, 0.22, 1.0],
                      [0.0, 0.0, 0.14, 0.22], [0.82, 0.78, 1.0, 1.0]],
    "min_damage": 10,
    "max_damage": 200000000,
    "combat_timeout": 3.0,
    "menu_detect": True,
    "menu_conf_thresh": 0.65,
    "menu_hysteresis_frames": 3,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def make_menu_detector(cfg: dict):
    """Создать (MenuClassifier, MenuHysteresis) если модель есть и детект включён.

    Возвращает None если models/menu_clf.onnx нет или menu_detect=false в конфиге —
    тогда метр работает без авто-паузы в меню (полагается на трекер+max_damage).
    """
    if not cfg.get("menu_detect", True):
        return None
    model = Path(__file__).parent / "models" / "menu_clf.onnx"
    if not model.exists():
        return None
    try:
        from menu_classifier import MenuClassifier, MenuHysteresis
    except ImportError:
        return None
    clf = MenuClassifier(str(model))
    hyst = MenuHysteresis(n_frames=cfg.get("menu_hysteresis_frames", 3))
    return (clf, hyst)


def process_frame(frame: np.ndarray, matcher: Matcher, tracker: DamageTracker,
                  cfg: dict, frame_h: int, now: float, menu_detector=None) -> None:
    """Распознать числа на кадре и обновить трекер.

    Args:
        frame: кадр BGR (из OpenCV или захвата)
        matcher: Matcher (CNN или template)
        tracker: DamageTracker
        cfg: config.json
        frame_h: высота кадра
        now: текущее время (time.monotonic())
        menu_detector: опц. (MenuClassifier, MenuHysteresis) — авто-пауза в меню.
            В меню (выбор способности/карта/инвентарь/завершение этапа) кадр НЕ
            обрабатываем: трекер не трогаем -> таймер боя замораживается сам.
            Гистерезис (3 кадра подряд) гасит одиночные ложные срабатывания.
    """
    if menu_detector is not None:
        clf, hyst = menu_detector
        raw = clf.is_menu(frame, confidence_threshold=cfg.get("menu_conf_thresh", 0.65))
        if hyst.update(raw):
            return  # стабильно меню -> пауза метра
    nums = matcher.recognize(frame, exclude_zones=cfg["exclude_zones"])
    # Размер НЕ отличает урон от мусора (урон бывает любого размера — далёкий враг,
    # отдалённая камера). Хил/золото отсекаются ЦВЕТОМ, HUD — ЗОНОЙ, иероглифы/надписи —
    # neg-классом CNN, HP — поведением. Фильтр высоты оставлен лишь как защита от
    # 1-2px шума маски (min_damage_height_frac мал по умолчанию).
    min_h = frame_h * cfg.get("min_damage_height_frac", 0.006)
    cand = [n for n in nums if n["h"] > min_h]
    tracker.update(cand, now)  # layer уже в числах из matcher.recognize()


def run_video(path: str, cfg: dict) -> None:
    matcher = Matcher(min_digit_frac=cfg.get("min_damage_height_frac_floor", 0.012))
    tracker = DamageTracker(dps_window=cfg["dps_window_sec"],
                            min_damage=cfg.get("min_damage", 10),
                            max_damage=cfg.get("max_damage", 200000000))
    menu_detector = make_menu_detector(cfg)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"Не открыть видео: {path}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(fps / 10))     # ~10 обработок/сек
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fi = 0
    last = 0.0
    print("Прогон видео. t(с) | DPS | урон/окно | ударов")
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if fi % step == 0:
            now = fi / fps
            process_frame(fr, matcher, tracker, cfg, h, now, menu_detector)
            if now - last >= 1.0:
                print(f"{now:7.1f} | {tracker.dps():7.0f} | {tracker.window_total():8d} | {tracker.hits()}")
                last = now
        fi += 1
    cap.release()
    print(f"Итого урона: {tracker.total_session}")


def _roi_box(cfg: dict, w: int, h: int) -> tuple[int, int, int, int] | None:
    """Прямоугольник зоны интереса (где всплывает урон), в пикселях.

    Урон в Ронине летит над персонажем — это центр экрана, а не края.
    Обрабатываем только этот прямоугольник -> CNN-сегментация работает по куда
    меньшей картинке, нагрузка на CPU падает в разы. Края (UI, чат, HP-бар внизу)
    не сканируем вовсе. Возвращаем None если roi выключен в конфиге.
    """
    roi = cfg.get("roi_frac")
    if not roi:
        return None
    x1 = int(roi[0] * w)
    y1 = int(roi[1] * h)
    x2 = int(roi[2] * w)
    y2 = int(roi[3] * h)
    return (x1, y1, x2, y2)


def run_realtime(cfg: dict) -> None:
    import queue
    import threading
    from capture import WindowCapture            # нужен только в realtime
    sys.path.insert(0, str(Path(__file__).parent / "ui"))
    from overlay import DpsOverlay, select_region

    # Выбор области захвата РАМКОЙ МЫШЬЮ (как OBS region) — не зависит от эмулятора.
    # Прошлую рамку храним в config (capture_region), чтобы не обводить каждый раз.
    region = cfg.get("capture_region")
    saved = tuple(region) if region and len(region) == 4 else None
    # Если рамки нет ИЛИ юзер просит переобвести (--pick) — рисуем заново.
    if saved is None or cfg.get("force_pick_region"):
        print("Обведите игровое поле мышью (Esc — отмена)...")
        picked = select_region(preset=saved)
        if picked is None:
            if saved is None:
                print("Область не выбрана. Запусти снова и обведи игровое поле.")
                return
            picked = saved   # отменил — используем прошлую
        region = list(picked)
        # сохранить в config для след. запусков (без временного флага force_pick_region)
        cfg["capture_region"] = region
        to_save = {k: v for k, v in cfg.items() if k != "force_pick_region"}
        try:
            CONFIG_PATH.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    try:
        cap = WindowCapture("", target_fps=cfg.get("capture_fps", 60),
                            region=tuple(region))
    except RuntimeError as e:
        print(e)
        return
    print(f"Область: {cap.width}x{cap.height} @ ({cap.left},{cap.top}) | захват: {cap.backend}")
    matcher = Matcher(min_digit_frac=cfg.get("min_damage_height_frac_floor", 0.012))
    tracker = DamageTracker(
        dps_window=cfg["dps_window_sec"],
        min_damage=cfg.get("min_damage", 10),
        max_damage=cfg.get("max_damage", 200000000),
        combat_timeout=cfg.get("combat_timeout", 3.0)
    )
    menu_detector = make_menu_detector(cfg)
    if menu_detector:
        print("Авто-пауза в меню: включена (menu_clf.onnx)")

    def on_reset() -> None:
        """Сброс метрик из кнопки Reset в оверлее."""
        tracker.reset()
        print("Метрики сброшены.")

    overlay = DpsOverlay(window_sec=cfg["dps_window_sec"], on_reset=on_reset)

    # ── Producer-consumer (CPU-only) ─────────────────────────────────────────
    # Проблема: один поток "захват+CNN" не успевает за уплывающим уроном, а
    # throttle/frame-diff пропускали кадры с уроном. Решение без GPU:
    #   producer  — поток захвата, кладёт СВЕЖАЙШИЙ кадр в очередь размера 1
    #               (старый выкидывает -> никогда не копим лаг);
    #   consumer  — поток CNN-распознавания, берёт кадр и обновляет трекер.
    # Если CNN не успевает — producer просто перезапишет кадр; захват не блокируется,
    # урон не теряется (берём всегда последний реальный кадр, а не каждый N-й по таймеру).
    stop_evt = threading.Event()
    frame_q: queue.Queue = queue.Queue(maxsize=1)
    roi = _roi_box(cfg, cap.width, cap.height)

    def producer() -> None:
        while not stop_evt.is_set():
            frame = cap.grab()
            if frame is None:
                continue
            now = time.monotonic()
            # выкинуть несъеденный старый кадр -> в очереди всегда самый свежий
            try:
                frame_q.get_nowait()
            except queue.Empty:
                pass
            try:
                frame_q.put_nowait((frame, now))
            except queue.Full:
                pass

    debug_log = cfg.get("debug_log")   # путь к файлу лога засчитанных ударов (опц.)
    _seen = [0]

    def consumer() -> None:
        while not stop_evt.is_set():
            try:
                frame, now = frame_q.get(timeout=0.2)
            except queue.Empty:
                continue
            # Детект меню — ВСЕГДА по полному кадру (UI-карточки по всему экрану),
            # распознавание урона — по ROI если включён.
            if menu_detector is not None:
                clf, hyst = menu_detector
                raw = clf.is_menu(frame, confidence_threshold=cfg.get("menu_conf_thresh", 0.65))
                if hyst.update(raw):
                    continue  # стабильно меню -> пауза, кадр не обрабатываем
            if roi is not None:
                x1, y1, x2, y2 = roi
                sub = frame[y1:y2, x1:x2]
                process_frame(sub, matcher, tracker, cfg, cap.height, now)
            else:
                process_frame(frame, matcher, tracker, cfg, cap.height, now)
            # отладочный лог: писать новые засчитанные удары (из необрезаемого hit_log)
            if debug_log and len(tracker.hit_log) != _seen[0]:
                try:
                    with open(debug_log, "a", encoding="utf-8") as f:
                        for (et, ev, el) in tracker.hit_log[_seen[0]:]:
                            f.write(f"{et:.2f}\t{ev}\t{el}\n")
                except OSError:
                    pass
                _seen[0] = len(tracker.hit_log)

    th_prod = threading.Thread(target=producer, daemon=True)
    th_cons = threading.Thread(target=consumer, daemon=True)
    th_prod.start()
    th_cons.start()

    print("Слежение пошло. Закрой окошко DPS чтобы выйти.")
    # Главный поток — ТОЛЬКО UI (Tkinter обязан жить в главном потоке).
    try:
        while not overlay.closed:
            overlay.update_stats(
                dps=tracker.dps(),
                peak_dps=tracker.peak_dps,
                avg_dps=tracker.avg_dps(),                 # activity DPS
                effective_dps=tracker.effective_dps(),     # главная цифра (как Details)
                window_total=tracker.window_total(),
                hits=tracker.hits(),
                total=tracker.total_session,
                crit_rate=tracker.crit_rate(),
                max_hit=tracker.max_hit,
                combat_time=tracker.combat_time()
            )
            overlay.pump()
            time.sleep(0.1)   # UI обновляем 10 раз/сек, CPU отдаём потокам
    finally:
        stop_evt.set()
        th_prod.join(timeout=1.0)
        th_cons.join(timeout=1.0)
        cap.stop()


def main() -> None:
    ap = argparse.ArgumentParser(description="Ronin DPS meter (vision-based, no mod)")
    ap.add_argument("--window", help="часть заголовка окна эмулятора")
    ap.add_argument("--video", help="прогон по видеозаписи")
    ap.add_argument("--list-windows", action="store_true")
    ap.add_argument("--pick", action="store_true",
                    help="заново обвести игровое поле рамкой мышью")
    args = ap.parse_args()

    cfg = load_config()
    if args.window:
        cfg["window_title"] = args.window
    if args.pick:
        cfg["force_pick_region"] = True

    if args.list_windows:
        from capture import list_windows
        for t in list_windows():
            print(t)
        return
    if args.video:
        run_video(args.video, cfg)
        return
    run_realtime(cfg)


if __name__ == "__main__":
    main()

