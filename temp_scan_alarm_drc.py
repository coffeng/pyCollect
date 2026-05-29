import argparse
import csv
import os
import struct
from dataclasses import dataclass


HEADER_SIZE = 40
DRI_MT_ALARM = 4
HEADER_STRUCT = struct.Struct('< h b b H I b b H h ' + 'h b' * 8)


@dataclass
class ScanResult:
    path: str
    alarm_records: int
    total_records: int
    size_bytes: int


def count_alarm_records(drc_path: str) -> ScanResult:
    alarm_count = 0
    total_count = 0

    with open(drc_path, 'rb') as f:
        while True:
            header = f.read(HEADER_SIZE)
            if len(header) < HEADER_SIZE:
                break

            try:
                unpacked = HEADER_STRUCT.unpack(header)
            except struct.error:
                break

            r_len = int(unpacked[0])
            r_maintype = int(unpacked[8])

            # Guard against corrupted lengths to keep scan fast and safe.
            if r_len < HEADER_SIZE or r_len > 5000:
                break

            total_count += 1
            if r_maintype == DRI_MT_ALARM:
                alarm_count += 1

            to_skip = r_len - HEADER_SIZE
            if to_skip > 0:
                f.seek(to_skip, os.SEEK_CUR)

    return ScanResult(
        path=drc_path,
        alarm_records=alarm_count,
        total_records=total_count,
        size_bytes=os.path.getsize(drc_path),
    )


def iter_drc_files(root_dir: str):
    for base, _dirs, files in os.walk(root_dir):
        for name in files:
            if name.lower().endswith('.drc'):
                yield os.path.join(base, name)


def main():
    parser = argparse.ArgumentParser(description='Fast DRC alarm-record scanner')
    parser.add_argument('root_dir', help='Root folder to search recursively for .drc files')
    parser.add_argument('--min-alarms', type=int, default=10, help='Minimum alarm record count')
    parser.add_argument(
        '--out-csv',
        default='output/alarm_rich_drc_candidates.csv',
        help='CSV output path for matching files',
    )
    args = parser.parse_args()

    root_dir = os.path.abspath(args.root_dir)
    matches = []
    scanned = 0

    for drc_path in iter_drc_files(root_dir):
        scanned += 1
        try:
            result = count_alarm_records(drc_path)
        except Exception:
            continue

        if result.alarm_records > args.min_alarms:
            matches.append(result)

    matches.sort(key=lambda r: r.alarm_records, reverse=True)

    out_csv = os.path.abspath(args.out_csv)
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['AlarmRecords', 'TotalRecords', 'SizeMB', 'Path'])
        for m in matches:
            writer.writerow([
                m.alarm_records,
                m.total_records,
                f'{m.size_bytes / (1024 * 1024):.2f}',
                m.path,
            ])

    print(f'Scanned DRC files: {scanned}')
    print(f'Matches (alarm_records > {args.min_alarms}): {len(matches)}')
    print(f'CSV: {out_csv}')
    if matches:
        print('Top matches:')
        for m in matches[:30]:
            size_mb = m.size_bytes / (1024 * 1024)
            print(f'  {m.alarm_records:5d} alarms | {m.total_records:7d} records | {size_mb:8.2f} MB | {m.path}')


if __name__ == '__main__':
    main()
