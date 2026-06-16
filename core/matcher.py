# -*- coding: utf-8 -*-
"""
Объединённый матчер: белый слой (обычный урон + HP) + красный (крит).
Использует CNN если есть обученная модель, иначе откатывается на template matching.
Возвращает числа из обоих слоёв с пометкой layer ('white'/'red').
"""
from __future__ import annotations
from pathlib import Path

import numpy as np

_MODEL = Path(__file__).parent.parent / "models" / "digit_cnn.onnx"


class Matcher:
    def __init__(self, conf_thresh: float = 0.85,
                 min_digit_frac: float = 0.012, max_digit_frac: float = 0.12) -> None:
        self.use_cnn = _MODEL.exists()
        if self.use_cnn:
            from cnn_matcher import CnnMatcher
            self.white = CnnMatcher("white", conf_thresh, min_digit_frac, max_digit_frac)
            self.red = CnnMatcher("red", conf_thresh, min_digit_frac, max_digit_frac)
            self.backend = "cnn"
        else:
            from digit_matcher import DigitMatcher
            self.white = DigitMatcher("white", match_thresh=0.72,
                                      min_digit_frac=min_digit_frac, max_digit_frac=max_digit_frac)
            self.red = None     # template-режим: только белый (red-эталонов нет)
            self.backend = "template"

    def recognize(self, bgr: np.ndarray, exclude_zones=None) -> list[dict]:
        nums = self.white.recognize(bgr, exclude_zones=exclude_zones)
        for n in nums:
            n["layer"] = "white"
        if self.red is not None:
            rnums = self.red.recognize(bgr, exclude_zones=exclude_zones)
            for n in rnums:
                n["layer"] = "red"
            nums.extend(rnums)
        return nums
