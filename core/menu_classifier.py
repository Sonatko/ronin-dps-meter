"""
Menu vs Battle frame classifier using ONNX model.
Detects UI menu screens to pause DPS meter.
"""

import onnxruntime as rt
import cv2
import numpy as np
from pathlib import Path


class MenuClassifier:
    """
    Classifies frames as either battle or menu.
    Input: 96x96 RGB frames
    Output: True if menu, False if battle
    """

    def __init__(self, model_path="models/menu_clf.onnx"):
        """
        Initialize the classifier.

        Args:
            model_path: Path to the ONNX model file.
        """
        self.model_path = Path(model_path)

        # Load ONNX model
        sess_options = rt.SessionOptions()
        sess_options.intra_op_num_threads = 1  # Lightweight - single thread
        sess_options.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL

        self.session = rt.InferenceSession(
            str(self.model_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        # Get input/output names
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def is_menu(self, bgr_frame, confidence_threshold: float = 0.65) -> bool:
        """
        Classify a single frame as menu or battle.

        Args:
            bgr_frame: BGR image (numpy array, H x W x 3, uint8)
            confidence_threshold: Minimum confidence for menu classification (default 0.65).
                                  Higher = fewer false positives (less pausing battle),
                                  but might miss some menus.

        Returns:
            bool: True if frame is confidently menu, False if battle or uncertain.
        """
        # Resize to 96x96
        frame_resized = cv2.resize(bgr_frame, (96, 96))

        # Convert BGR to RGB (CRITICAL: must match training preprocessing)
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

        # Normalize to [0, 1]
        frame_norm = frame_rgb.astype(np.float32) / 255.0

        # CHW format (CRITICAL: must match training)
        frame_chw = np.transpose(frame_norm, (2, 0, 1))

        # Add batch dimension
        input_data = np.expand_dims(frame_chw, axis=0)

        # Inference
        outputs = self.session.run([self.output_name], {self.input_name: input_data})
        logits = outputs[0]  # Shape: (1, 2)

        # Get probabilities
        probs = self._softmax(logits[0])
        menu_confidence = float(probs[1])

        # Menu only if confidence exceeds threshold
        return menu_confidence >= confidence_threshold

    def get_confidence(self, bgr_frame):
        """
        Get confidence scores for both classes.

        Args:
            bgr_frame: BGR image (numpy array, H x W x 3, uint8)

        Returns:
            tuple: (battle_confidence, menu_confidence) both in [0, 1]
        """
        # Resize to 96x96
        frame_resized = cv2.resize(bgr_frame, (96, 96))

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

        # Normalize to [0, 1]
        frame_norm = frame_rgb.astype(np.float32) / 255.0

        # CHW format
        frame_chw = np.transpose(frame_norm, (2, 0, 1))

        # Add batch dimension
        input_data = np.expand_dims(frame_chw, axis=0)

        # Inference
        outputs = self.session.run([self.output_name], {self.input_name: input_data})
        logits = outputs[0]  # Shape: (1, 2)

        # Get probabilities
        probs = self._softmax(logits[0])

        return float(probs[0]), float(probs[1])

    @staticmethod
    def _softmax(x):
        """Apply softmax."""
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()


class MenuHysteresis:
    """
    Helper for frame classification with hysteresis.

    Reduces false positives by requiring N consecutive menu frames before pausing.
    Returns battle immediately (no hysteresis on battle side).

    Usage in process_frame():
        hysteresis = MenuHysteresis(n_frames=3)

        in frame loop:
            is_menu_raw = clf.is_menu(frame, confidence_threshold=0.65)
            is_menu_stable = hysteresis.update(is_menu_raw)

            if is_menu_stable:
                pause_dps_meter()
            else:
                continue_tracking()
    """

    def __init__(self, n_frames: int = 3):
        """
        Initialize hysteresis.

        Args:
            n_frames: Number of consecutive menu frames required to trigger pause.
        """
        self.n_frames = n_frames
        self.menu_count = 0

    def update(self, is_menu_raw: bool) -> bool:
        """
        Update hysteresis counter and return stable menu state.

        Args:
            is_menu_raw: Raw classification from is_menu().

        Returns:
            bool: True if N consecutive menu frames detected, False otherwise.
        """
        if is_menu_raw:
            self.menu_count += 1
            return self.menu_count >= self.n_frames
        else:
            # Reset immediately on battle detection (no hysteresis for false negatives)
            self.menu_count = 0
            return False

    def reset(self):
        """Reset hysteresis counter."""
        self.menu_count = 0


if __name__ == "__main__":
    # Simple test
    clf = MenuClassifier()
    print("✓ MenuClassifier loaded successfully")

    # Test with dummy frame
    dummy_frame = np.ones((480, 320, 3), dtype=np.uint8) * 100
    is_menu = clf.is_menu(dummy_frame)
    battle_conf, menu_conf = clf.get_confidence(dummy_frame)

    print(f"Test frame - Menu: {is_menu}, Battle conf: {battle_conf:.3f}, Menu conf: {menu_conf:.3f}")

    # Test hysteresis
    print("\nHysteresis test:")
    hysteresis = MenuHysteresis(n_frames=3)
    raw_sequence = [True, True, True, False, False]
    for i, raw in enumerate(raw_sequence):
        stable = hysteresis.update(raw)
        print(f"  Frame {i}: raw={raw} -> stable={stable} (count={hysteresis.menu_count})")
