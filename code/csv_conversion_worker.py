"""CSV conversion worker thread for pyCollect GUI."""
import struct
from pathlib import Path

from PyQt5 import QtCore

import drc_2_csv


class CsvConversionWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(int, int, int)
    finished_signal = QtCore.pyqtSignal(object)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, drc_path, params_path, waves_path, parent=None):
        super().__init__(parent)
        self.drc_path = Path(drc_path)
        self.params_path = Path(params_path)
        self.waves_path = Path(waves_path)

    def _count_records(self):
        total = 0
        with self.drc_path.open("rb") as fp:
            while True:
                header = fp.read(40)
                if len(header) < 40:
                    break
                r_len = struct.unpack_from("<h", header, 0)[0]
                if r_len < 40:
                    break
                total += 1
                skip = r_len - 40
                if skip > 0:
                    fp.seek(skip, 1)
        return max(0, int(total))

    def run(self):
        try:
            total_records = self._count_records()
            self.progress_signal.emit(1, 0, total_records)

            params_df = drc_2_csv.read_params_file(str(self.params_path))
            waves_df = drc_2_csv.read_waves_file(str(self.waves_path))

            def on_progress(processed, _total):
                total = total_records if total_records > 0 else int(_total or 0)
                if total > 0:
                    pct = int(min(90, max(1, (float(processed) * 90.0) / total)))
                else:
                    pct = 45
                self.progress_signal.emit(pct, int(processed), int(total))

            trend_df, wave_df, freq, pacer_info_list, alarms_df = (
                drc_2_csv.process_drc_file(
                    str(self.drc_path),
                    params_df,
                    waves_df,
                    logger=None,
                    progress_cb=on_progress,
                    total_records=(total_records if total_records > 0 else None),
                )
            )

            saved_paths = []
            trend_csv_path = str(self.drc_path).replace(".drc", "_trends.csv")
            drc_2_csv.save_dataframe_to_csv(trend_df, trend_csv_path, logger=None)
            saved_paths.append(trend_csv_path)
            self.progress_signal.emit(95, total_records, total_records)

            if freq > 0 and wave_df is not None:
                wave_csv_path = str(self.drc_path).replace(".drc", "_waves.csv")
                drc_2_csv.save_dataframe_to_csv(wave_df, wave_csv_path, logger=None)
                saved_paths.append(wave_csv_path)
                self.progress_signal.emit(98, total_records, total_records)

            if len(pacer_info_list) > 1:
                drc_2_csv.save_pacers_to_csv(pacer_info_list, str(self.drc_path))
                saved_paths.append(str(self.drc_path).replace(".drc", "_pacers.csv"))

            if alarms_df is not None and len(alarms_df) > 0:
                drc_2_csv.save_alarms_to_csv(alarms_df, str(self.drc_path))
                saved_paths.append(str(self.drc_path).replace(".drc", "_alarms.csv"))

            self.progress_signal.emit(100, total_records, total_records)
            self.finished_signal.emit(saved_paths)
        except Exception as exc:
            self.error_signal.emit(str(exc))
