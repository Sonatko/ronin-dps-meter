# -*- coding: utf-8 -*-
"""
Распознавание чисел через CNN (ONNX) — замена хрупкого template matching.

Сегментация цифр по контурам цветовой маски (white/red слои), классификация
каждого глифа крошечным CNN. Инференс через onnxruntime (CPU, лёгкий, без torch).

Группировка цифр в числа — кластеризация по строке + разрыв по X-зазору.
"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

GLYPH = 28
MODEL = Path(__file__).parent.parent / "models" / "digit_cnn.onnx"


def _norm_glyph(mask_roi: np.ndarray) -> np.ndarray:
    """Глиф -> 28x28 вписанный с центрированием (как при обучении)."""
    h, w = mask_roi.shape
    scale = 20.0 / max(h, w)
    nh, nw = max(1, int(h * scale)), max(1, int(w * scale))
    small = cv2.resize(mask_roi, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((GLYPH, GLYPH), dtype=np.uint8)
    oy, ox = (GLYPH - nh) // 2, (GLYPH - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = small
    return canvas


class CnnMatcher:
    def __init__(self, layer: str = "white", conf_thresh: float = 0.85,
                 min_digit_frac: float = 0.012, max_digit_frac: float = 0.12) -> None:
        if not MODEL.exists():
            raise RuntimeError(f"Нет модели {MODEL}. Сначала обучи: tools/train_cnn.py")
        self.layer = layer
        self.conf = conf_thresh
        self.min_frac = min_digit_frac
        self.max_frac = max_digit_frac
        # ограничиваем потоки onnxruntime — сеть крошечная, не нужно занимать все ядра
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(MODEL), sess_options=so,
                                         providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name

    def _mask(self, bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        if self.layer == "white":
            mask = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([179, 55, 255]))
        else:
            r1 = cv2.inRange(hsv, np.array([0, 90, 110]), np.array([12, 255, 255]))
            r2 = cv2.inRange(hsv, np.array([166, 90, 110]), np.array([179, 255, 255]))
            mask = cv2.bitwise_or(r1, r2)
        # ВЫЧЕСТЬ хил (зелёный) и золото (жёлтый) — это НЕ урон (см. карту цветов Ronin).
        # Гасим их пиксели из обоих слоёв до сегментации, чтобы числа хила/золота
        # гарантированно не попали в подсчёт DPS, даже если протекли в белую/красную маску.
        green = cv2.inRange(hsv, np.array([40, 70, 70]), np.array([85, 255, 255]))
        yellow = cv2.inRange(hsv, np.array([20, 80, 120]), np.array([35, 255, 255]))
        ignore = cv2.bitwise_or(green, yellow)
        return cv2.bitwise_and(mask, cv2.bitwise_not(ignore))

    def _classify_batch(self, glyphs: list[np.ndarray]) -> list[tuple[int, float]]:
        if not glyphs:
            return []
        batch = np.stack([g.astype(np.float32) / 255.0 for g in glyphs])[:, None, :, :]
        logits = self.sess.run(None, {self.inp: batch})[0]
        # softmax -> уверенность
        ex = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = ex / ex.sum(axis=1, keepdims=True)
        out = []
        for row in probs:
            d = int(row.argmax())
            # Класс 10 = негатив (мусор) -> скипнуть, вернуть спецмаркер -1
            if d == 10:
                out.append((-1, float(row[d])))
            else:
                out.append((d, float(row[d])))
        return out

    def recognize(self, bgr: np.ndarray, exclude_zones=None) -> list[dict]:
        H, W = bgr.shape[:2]
        min_h, max_h = int(H * self.min_frac), int(H * self.max_frac)
        mask = self._mask(bgr)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cand_boxes, cand_glyphs = [], []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if h < min_h or h > max_h or w < 3 or w > h * 1.2:
                continue
            if cv2.contourArea(c) < (min_h * 2):
                continue
            if exclude_zones:
                cxf, cyf = (x + w / 2) / W, (y + h / 2) / H
                if any(zx0 <= cxf <= zx1 and zy0 <= cyf <= zy1
                       for (zx0, zy0, zx1, zy1) in exclude_zones):
                    continue
            cand_boxes.append((x, y, w, h))
            cand_glyphs.append(_norm_glyph(mask[y:y + h, x:x + w]))
        preds = self._classify_batch(cand_glyphs)
        glyphs = []
        for (x, y, w, h), (dig, sc) in zip(cand_boxes, preds):
            # Пропустить негативы (класс 10 -> маркер -1)
            if dig == -1:
                continue
            if sc >= self.conf:
                glyphs.append((x, y, w, h, str(dig), sc))
        numbers = self._group(glyphs)
        # Отсев HP игрока: HP ВСЕГДА на красной полоске-баре (см. карту Ronin).
        # Если рядом с белым числом есть горизонтальный красный бар — это HP, не урон.
        # Только для белого слоя (красный урон полосок не имеет).
        if self.layer == "white" and numbers:
            numbers = [n for n in numbers if not self._has_red_bar_near(bgr, n)]
        return numbers

    @staticmethod
    def _has_red_bar_near(bgr: np.ndarray, num: dict) -> bool:
        """Есть ли горизонтальный красный HP-бар рядом с числом (над/под/вокруг).

        HP в Ronin = белое число НА красной полоске. У уплывающего урона полоски нет.
        Берём зону вокруг бокса числа, ищем красные пиксели большой горизонтальной
        протяжённости (бар, а не отдельные красные циферки крита).
        """
        H, W = bgr.shape[:2]
        x, y, h = num["x"], num["y"], num["h"]
        # ширину числа не знаем точно (есть только x первого глифа); берём ~ по высоте
        w = max(num.get("h", h) * 3, 40)
        # зона поиска бара: чуть шире числа, полоса над и под (HP-бар обычно под/над числом)
        pad_x = int(w * 0.6)
        x0 = max(0, int(x - pad_x))
        x1 = min(W, int(x + w + pad_x))
        y0 = max(0, int(y - h * 1.2))
        y1 = min(H, int(y + h * 2.2))
        roi = bgr[y0:y1, x0:x1]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        r1 = cv2.inRange(hsv, np.array([0, 90, 80]), np.array([12, 255, 255]))
        r2 = cv2.inRange(hsv, np.array([166, 90, 80]), np.array([179, 255, 255]))
        red = cv2.bitwise_or(r1, r2)
        # бар = длинная горизонтальная полоса красного: ищем строку с большой долей красного
        if red.shape[1] < 10:
            return False
        row_frac = red.mean(axis=1) / 255.0   # доля красного в каждой строке
        # HP-бар: хотя бы одна строка где >=50% ширины зоны красная (сплошная полоска)
        return bool(row_frac.max() >= 0.5)

    def _group(self, glyphs):
        if not glyphs:
            return []
        glyphs_sorted = sorted(glyphs, key=lambda g: g[1])
        rows, current = [], [glyphs_sorted[0]]
        ref_y, ref_h = glyphs_sorted[0][1], glyphs_sorted[0][3]
        for g in glyphs_sorted[1:]:
            if abs(g[3] - ref_h) < ref_h * 0.3 and abs(g[1] - ref_y) < ref_h * 0.4:
                current.append(g)
            else:
                rows.append(current); current = [g]; ref_y, ref_h = g[1], g[3]
        rows.append(current)
        numbers = []
        for row in rows:
            row.sort(key=lambda g: g[0])
            chunk = [row[0]]
            for k in range(1, len(row)):
                prev, cur = chunk[-1], row[k]
                gap = cur[0] - (prev[0] + prev[2])
                if gap >= ((prev[2] + cur[2]) / 2) * 1.5:
                    self._emit(chunk, numbers); chunk = [cur]
                else:
                    chunk.append(cur)
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
        # Анти-мусор фона: тушевый фон Ronin (штрихи/ограды) -> серии палочек `1`,
        # CNN склеивает в нереальные числа (11111051101, 311111, 111111).
        # ВАЖНО: реальный урон бывает 20 млн = "20000000" (серия нулей!) — НЕ резать
        # по серии одинаковых цифр. Режем только КАШУ ИЗ ЕДИНИЦ:
        #   доля единиц очень высокая И единиц >=4. `20000000`/`306985` пройдут.
        ones = digits.count("1")
        if ones >= 4 and ones / len(digits) >= 0.7:
            return
        avg = sum(c[5] for c in chunk) / len(chunk)
        numbers.append({"value": val, "x": chunk[0][0], "y": chunk[0][1],
                        "h": chunk[0][3], "conf": round(avg, 2),
                        "layer": getattr(chunk[0], "layer", None)})
