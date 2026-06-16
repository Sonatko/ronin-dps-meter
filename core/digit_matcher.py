# -*- coding: utf-8 -*-
"""
Движок распознавания чисел через template matching (БЕЗ нейро-OCR).
Шрифт Ронина фиксирован -> matchTemplate цифр 0-9.

SCALE-INVARIANT (для любого разрешения у людей):
  - всё считается в ДОЛЯХ высоты окна, не в пикселях (совет exa/dsp.stackexchange)
  - кандидат и эталон нормализуются к 48px, grayscale (совет exa/dev.to)
  - размер цифры урона ~ % высоты экрана (Unity Canvas Scaler масштабирует UI)
  - порог матчинга 0.85, не выше (совет exa/dev.to)

Карта чисел Ronin (финальная):
  УРОН   = крупное целое, белое(обычн)/красное(крит), уплывает вверх -> СЧИТАЕМ
  HP     = белое над красным баром, статично                        -> отсев (трекинг)
  СТАН   = с запятой/точкой, значение 0.1-11, мелкое                 -> отсев (тут по '.'/',' нельзя — режем числа, фильтр в трекере по величине/позиции)
  уровень/FPS = фикс-зоны экрана                                     -> отсев по доле координат
  хил    = зелёный                                                   -> отсев (не белый/красный слой)
"""
import os, cv2, numpy as np, glob

TPL_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
NORM_H = 48                    # высота нормализации глифа
MATCH_THRESH = 0.60            # порог совпадения (не выше 0.9 — совет exa)


class DigitMatcher:
    def __init__(self, layer="white", match_thresh=MATCH_THRESH,
                 min_digit_frac=0.012, max_digit_frac=0.10):
        """
        min/max_digit_frac — высота цифры как доля высоты КАДРА.
        ~1.2%..10% покрывает и мелкий урон, и крупный крит на любом разрешении.
        """
        self.layer = layer
        self.thresh = match_thresh
        self.min_frac = min_digit_frac
        self.max_frac = max_digit_frac
        self.templates = {}    # digit -> grayscale glyph normalized to NORM_H
        d = os.path.join(TPL_DIR, layer)
        for f in glob.glob(os.path.join(d, "[0-9].png")):
            dig = os.path.splitext(os.path.basename(f))[0]
            g = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
            if g is not None:
                # нормализуем эталон к NORM_H
                gw = max(1, int(g.shape[1] * NORM_H / g.shape[0]))
                self.templates[dig] = cv2.resize(g, (gw, NORM_H), interpolation=cv2.INTER_NEAREST)
        if not self.templates:
            raise RuntimeError(f"Нет эталонов в {d}")

    def _mask(self, bgr):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        if self.layer == "white":
            return cv2.inRange(hsv, np.array([0, 0, 200]), np.array([179, 55, 255]))
        r1 = cv2.inRange(hsv, np.array([0, 90, 110]), np.array([12, 255, 255]))
        r2 = cv2.inRange(hsv, np.array([166, 90, 110]), np.array([179, 255, 255]))
        return cv2.bitwise_or(r1, r2)

    def _match_glyph(self, glyph_mask):
        """Сопоставить вырезанный глиф (бинарная маска) со всеми эталонами. Возврат (digit, score)."""
        gw = max(1, int(glyph_mask.shape[1] * NORM_H / glyph_mask.shape[0]))
        g = cv2.resize(glyph_mask, (gw, NORM_H), interpolation=cv2.INTER_NEAREST)
        best_d, best_s = None, -1.0
        for dig, tpl in self.templates.items():
            # приводим эталон к ширине кандидата (та же высота NORM_H)
            t = cv2.resize(tpl, (gw, NORM_H), interpolation=cv2.INTER_NEAREST)
            res = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
            s = float(res.max())
            if s > best_s:
                best_s, best_d = s, dig
        return best_d, best_s

    def recognize(self, bgr, exclude_zones=None):
        """
        Вернуть список dict: {value, x, y, h, layer}.
        exclude_zones — список (x0f,y0f,x1f,y1f) в ДОЛЯХ кадра для отсева UI (FPS/уровень).
        """
        H, W = bgr.shape[:2]
        min_h = int(H * self.min_frac)
        max_h = int(H * self.max_frac)
        mask = self._mask(bgr)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        glyphs = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if h < min_h or h > max_h or w < 3 or w > h * 1.2:
                continue
            if cv2.contourArea(c) < (min_h * 2):
                continue
            # отсев UI-зон (доли экрана)
            if exclude_zones:
                cxf, cyf = (x + w / 2) / W, (y + h / 2) / H
                if any(zx0 <= cxf <= zx1 and zy0 <= cyf <= zy1
                       for (zx0, zy0, zx1, zy1) in exclude_zones):
                    continue
            dig, sc = self._match_glyph(mask[y:y+h, x:x+w])
            if dig is not None and sc >= self.thresh:
                glyphs.append((x, y, w, h, dig, sc))
        return self._group(glyphs)

    def _group(self, glyphs):
        """Сгруппировать цифры в числа.

        Алгоритм:
        1. Группируем цифры по строкам (похожая Y + высота)
        2. Внутри каждой строки сортируем по X и разбиваем на числа
        3. Для разбиения: если X-зазор > threshold, это разные числа
        4. Возвращаем результаты строк сверху вниз (по Y), а внутри строки слева направо
        """
        if not glyphs:
            return []

        # === ШАГ 1: Кластеризация по строкам (по Y+высота) ===
        # Используем простой подход: сортируем по Y, потом группируем близкие Y
        glyphs_sorted = sorted(glyphs, key=lambda g: g[1])  # Sort by Y
        rows = []
        if glyphs_sorted:
            current_row = [glyphs_sorted[0]]
            ref_y, ref_h = glyphs_sorted[0][1], glyphs_sorted[0][3]

            for i in range(1, len(glyphs_sorted)):
                g = glyphs_sorted[i]
                y, h = g[1], g[3]

                # Проверяем совместимость с ПЕРВОЙ цифрой строки
                height_compat = abs(h - ref_h) < ref_h * 0.3
                y_compat = abs(y - ref_y) < ref_h * 0.4  # Y-выравнивание

                if height_compat and y_compat:
                    current_row.append(g)
                else:
                    rows.append(current_row)
                    current_row = [g]
                    ref_y, ref_h = y, h

            rows.append(current_row)

        # === ШАГ 2: Сортировка строк по Y (сверху вниз) ===
        rows.sort(key=lambda row: row[0][1])

        # === ШАГ 3: Внутри каждой строки разбиваем на числа по X-зазорам ===
        numbers = []
        for row in rows:
            row.sort(key=lambda g: g[0])  # сортируем строку слева направо

            chunk = [row[0]]
            for i in range(1, len(row)):
                last_g = chunk[-1]
                cur_g = row[i]

                last_x, last_y, last_w, last_h, last_d, last_s = last_g
                cur_x, cur_y, cur_w, cur_h, cur_d, cur_s = cur_g

                x_gap = cur_x - (last_x + last_w)
                avg_width = (last_w + cur_w) / 2.0

                # Если зазор слишком большой, это новое число
                if x_gap >= avg_width * 1.5:
                    self._emit(chunk, numbers)
                    chunk = [cur_g]
                else:
                    chunk.append(cur_g)

            self._emit(chunk, numbers)

        return numbers

    @staticmethod
    def _emit(chunk, numbers):
        if not chunk:
            return
        digits = "".join(c[4] for c in chunk)
        try:
            val = int(digits)
        except ValueError:
            return
        avg_conf = sum(c[5] for c in chunk) / len(chunk)
        numbers.append({"value": val, "x": chunk[0][0], "y": chunk[0][1],
                        "h": chunk[0][3], "conf": round(avg_conf, 2)})


if __name__ == "__main__":
    m = DigitMatcher("white")
    print(f"Эталоны white: {sorted(m.templates.keys())}")
    # FPS внизу-слева, уровень вверху-слева -> отсекаем по долям
    EXCLUDE = [(0.0, 0.92, 0.20, 1.0),   # FPS низ-лево
               (0.0, 0.0, 0.10, 0.15)]   # уровень верх-лево
    for p in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "test-shots", "*.png"))):
        if "_masked" in p or "VIS" in p or "DBG" in p:
            continue
        bgr = cv2.imread(p)
        if bgr is None:
            continue
        nums = m.recognize(bgr, exclude_zones=EXCLUDE)
        print(f"{os.path.basename(p):16s}: {[n['value'] for n in nums]}")
