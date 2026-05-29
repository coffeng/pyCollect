"""Simple live matplotlib plot for first detected HR and ECG waveform.

Extracted from pycollect.py to keep that file under 1000 lines.
Used only by the terminal/headless capture path (--gui flag).
"""
import collections
import time


class LiveMonitorPlot:
    """Simple live plot for first detected heart rate and ECG waveform."""

    def __init__(
        self,
        hr_window_points=10,
        ecg_window_samples=5000,
        refresh_interval_sec=10,
        keep_foreground=True,
    ):
        try:
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError(
                "GUI mode requires matplotlib. "
                "Install it with: pip install matplotlib"
            ) from exc

        self.plt = plt
        self.hr_points = collections.deque(maxlen=hr_window_points)
        self.ecg_points = collections.deque(maxlen=ecg_window_samples)
        self.refresh_interval_sec = max(1, int(refresh_interval_sec))
        self.keep_foreground = keep_foreground
        self.last_draw_time = 0.0

        self.plt.ion()
        self.fig, (self.ax_hr, self.ax_ecg) = self.plt.subplots(
            2, 1, figsize=(10, 6)
        )
        self.fig.suptitle("pycollect Live View")

        self.hr_line, = self.ax_hr.plot([], [], "b-")
        self.ax_hr.set_title("Heart Rate (first detected trend value)")
        self.ax_hr.set_ylabel("bpm")
        self.ax_hr.grid(True, alpha=0.3)
        self.ax_hr.set_xlim(0, max(10, hr_window_points))
        self.ax_hr.set_ylim(40, 140)

        self.ecg_line, = self.ax_ecg.plot([], [], "r-")
        self.ax_ecg.set_title("ECG Waveform (first detected wave channel)")
        self.ax_ecg.set_ylabel("raw")
        self.ax_ecg.set_xlabel("sample")
        self.ax_ecg.grid(True, alpha=0.3)
        self.ax_ecg.set_xlim(0, max(200, ecg_window_samples))
        self.ax_ecg.set_ylim(-100, 100)

        self.status_text = self.fig.text(
            0.5, 0.01, "Waiting for HR/ECG data...",
            ha="center", va="bottom",
        )

        self.fig.tight_layout()
        self.fig.canvas.draw()
        self._show_and_raise_window()
        self._draw(force=True)

    def _show_and_raise_window(self):
        self.plt.show(block=False)
        manager = self.fig.canvas.manager
        window = getattr(manager, "window", None)
        if window is None or not self.keep_foreground:
            return
        try:
            if hasattr(window, "showNormal"):
                window.showNormal()
            if hasattr(window, "raise_"):
                window.raise_()
            if hasattr(window, "activateWindow"):
                window.activateWindow()
        except Exception:
            pass
        try:
            if hasattr(window, "attributes"):
                window.attributes("-topmost", 1)
                window.attributes("-topmost", 0)
            if hasattr(window, "wm_attributes"):
                window.wm_attributes("-topmost", 1)
                window.wm_attributes("-topmost", 0)
        except Exception:
            pass

    def _draw(self, force=False):
        now = time.time()
        if not force and (now - self.last_draw_time) < self.refresh_interval_sec:
            return
        self.last_draw_time = now
        hr_count = len(self.hr_points)
        ecg_count = len(self.ecg_points)
        self.status_text.set_text(
            f"Last {hr_count} HR points, {ecg_count} ECG samples | "
            f"refresh every {self.refresh_interval_sec}s"
        )
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        self.plt.pause(0.001)

    def update(self, hr_value=None, ecg_samples=None):
        if hr_value is not None:
            self.hr_points.append(hr_value)
        if ecg_samples:
            self.ecg_points.extend(ecg_samples)
        if self.hr_points:
            y_hr = list(self.hr_points)
            x_hr = list(range(len(y_hr)))
            self.hr_line.set_data(x_hr, y_hr)
            self.ax_hr.set_xlim(0, max(10, len(y_hr)))
            hr_min, hr_max = min(y_hr), max(y_hr)
            if hr_min == hr_max:
                hr_min -= 1; hr_max += 1
            self.ax_hr.set_ylim(hr_min - 2, hr_max + 2)
        if self.ecg_points:
            y_ecg = list(self.ecg_points)
            x_ecg = list(range(len(y_ecg)))
            self.ecg_line.set_data(x_ecg, y_ecg)
            self.ax_ecg.set_xlim(0, max(200, len(y_ecg)))
            ecg_min, ecg_max = min(y_ecg), max(y_ecg)
            if ecg_min == ecg_max:
                ecg_min -= 1; ecg_max += 1
            margin = max(2, int((ecg_max - ecg_min) * 0.1))
            self.ax_ecg.set_ylim(ecg_min - margin, ecg_max + margin)
        self._draw(force=False)

    def close(self):
        self.plt.ioff()
        self.plt.close(self.fig)
