"""原始 sEMG 数据集体检（只读）。

扫描 data/ 下所有受试者的 *_raw_data_*.txt，输出：
  1. 数据集概况（受试者数、文件数、总采样数）
  2. 文件格式校验（表头、列数、缺失值、读取失败）
  3. 时间轴与采样率（步长分布、缺口、推算采样率）
  4. 类别分布（全局）
  5. 受试者 × 类别（谁做了哪些手势）
  6. 异常与提示

不会修改 data/ 下的任何文件。

用法：
    python src/inspect_raw.py
    python src/inspect_raw.py --data-dir data --json report.json
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 常量

# 受试者目录名固定是两位数字，如 01 ~ 36
SUBJECT_RE = re.compile(r"^\d{2}$")

EXPECTED_COLUMNS = [
    "time",
    "channel1",
    "channel2",
    "channel3",
    "channel4",
    "channel5",
    "channel6",
    "channel7",
    "channel8",
    "class",
]

CLASS_NAMES = {
    0: "未标注",
    1: "手放松",
    2: "握拳",
    3: "腕屈",
    4: "腕伸",
    5: "桡侧偏",
    6: "尺侧偏",
    7: "伸掌",
}

# time 列以毫秒计，平均步长 d(ms) 对应采样率 1000/d
MS_PER_S = 1000.0

# 步长 >= 该值（毫秒）视为时间轴上的一个缺口
GAP_MS = 2

# 统计步长直方图时忽略超过该值（毫秒）的极端间隔
MAX_DT_MS = 10


# ---------------------------------------------------------------- 单文件体检


@dataclass
class FileStat:
    subject: str
    name: str
    path: Path
    size_bytes: int
    n_rows: int = 0
    n_cols: int = 0
    header_ok: bool = False
    header_seen: Optional[list] = None
    n_blank_rows: int = 0
    n_incomplete_rows: int = 0
    n_inf: int = 0
    time_monotonic: bool = True
    n_dup_time: int = 0
    dt_hist: Counter = field(default_factory=Counter)
    mean_dt_ms: float = float("nan")
    duration_ms: float = float("nan")
    class_counts: Counter = field(default_factory=Counter)
    error: Optional[str] = None


def inspect_file(path: Path) -> FileStat:
    """读取并体检单个文件；任何异常记录在 FileStat.error，不向外抛。"""
    stat = FileStat(
        subject=path.parent.name,
        name=path.name,
        path=path,
        size_bytes=path.stat().st_size,
    )

    try:
        # 第一行是表头，pandas 默认 header=0 正好对
        df = pd.read_csv(path, sep="\t")
    except Exception as exc:  # 体检脚本要尽量把剩下的文件读完
        stat.error = f"{type(exc).__name__}: {exc}"
        return stat

    stat.header_seen = list(df.columns)
    stat.header_ok = stat.header_seen == EXPECTED_COLUMNS
    stat.n_cols = df.shape[1]

    # 文件末尾可能有多余空行；个别文件（如 34/1）末行还会被截断在 channel8 处，
    # 缺少 class 列。两种情况都要丢掉，否则会污染行数和类别统计。
    n_raw = len(df)
    df = df.dropna(how="all")
    stat.n_blank_rows = n_raw - len(df)

    incomplete = df.isna().any(axis=1)
    stat.n_incomplete_rows = int(incomplete.sum())
    df = df[~incomplete]

    stat.n_rows = len(df)

    # read_csv 会把 "inf" 读成 inf，单独统计
    values = df.select_dtypes(include=[np.number]).to_numpy()
    if values.size:
        stat.n_inf = int(np.isinf(values).sum())

    # ---- 时间轴 ----
    if "time" in df.columns:
        t = pd.to_numeric(df["time"], errors="coerce")
        dt = t.diff().dropna()
        stat.time_monotonic = bool((dt >= 0).all())
        stat.n_dup_time = int((dt == 0).sum())
        buckets = dt[(dt > 0) & (dt <= MAX_DT_MS)].astype(int)
        stat.dt_hist = Counter(buckets.tolist())
        if len(dt):
            stat.mean_dt_ms = float(dt.mean())
            stat.duration_ms = float(t.iloc[-1] - t.iloc[0])

    # ---- 类别 ----
    if "class" in df.columns:
        # 上面已丢弃含 NaN 的行，此处标签必定是数值
        labels = pd.to_numeric(df["class"], errors="coerce")
        stat.class_counts = Counter(labels.round().astype(int).tolist())

    return stat


# ---------------------------------------------------------------- 汇总


def collect(stats: list) -> dict:
    total_rows = sum(s.n_rows for s in stats)
    total_bytes = sum(s.size_bytes for s in stats)

    dt_hist = Counter()
    for s in stats:
        dt_hist.update(s.dt_hist)
    n_dt = sum(dt_hist.values())
    mean_dt = sum(k * v for k, v in dt_hist.items()) / n_dt if n_dt else float("nan")

    class_counts = Counter()
    for s in stats:
        class_counts.update(s.class_counts)

    per_subject = {}
    files_per_subject = Counter()
    for s in stats:
        per_subject.setdefault(s.subject, set()).update(s.class_counts)
        files_per_subject[s.subject] += 1

    return {
        "n_files": len(stats),
        "n_subjects": len(per_subject),
        "total_rows": total_rows,
        "total_bytes": total_bytes,
        "dt_hist": dt_hist,
        "n_dt": n_dt,
        "mean_dt_ms": mean_dt,
        "class_counts": class_counts,
        "per_subject": per_subject,
        "files_per_subject": files_per_subject,
    }


# ---------------------------------------------------------------- 报告


def pct(part: float, whole: float) -> str:
    return "   n/a" if not whole else f"{100.0 * part / whole:5.1f}%"


def human_bytes(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def print_report(stats: list, agg: dict, data_dir: Path, warnings: list) -> None:
    bar = "=" * 62
    subjects = sorted(agg["per_subject"])

    # ---- 1 概况 ----
    print(bar)
    print(" 1. 数据集概况")
    print(bar)
    print(f"  数据目录  : {data_dir}")
    print(f"  受试者数  : {agg['n_subjects']}  ({subjects[0]}–{subjects[-1]})")
    print(f"  文件数    : {agg['n_files']}")
    print(f"  总大小    : {human_bytes(agg['total_bytes'])}")
    print(f"  总采样数  : {agg['total_rows']:,}")
    counts = Counter(agg["files_per_subject"].values())
    print("  文件数分布: " + "，".join(f"{n} 个文件 × {c} 人" for n, c in sorted(counts.items())))
    print()

    # ---- 2 格式 ----
    print(bar)
    print(" 2. 文件格式校验")
    print(bar)
    bad_header = [s for s in stats if not s.header_ok]
    bad_width = [s for s in stats if s.n_cols and s.n_cols != len(EXPECTED_COLUMNS)]
    dropped = [s for s in stats if s.n_blank_rows or s.n_incomplete_rows]
    bad_inf = [s for s in stats if s.n_inf]
    errored = [s for s in stats if s.error]

    if bad_header:
        print(f"  表头      : 否，{len(bad_header)} 个文件异常")
    else:
        print(f"  表头      : 是，全部 {len(stats)} 个文件一致")
    print(f"  列数      : {len(EXPECTED_COLUMNS)} 列" + ("（全部一致）" if not bad_width else f"，{len(bad_width)} 个文件不一致"))
    if dropped:
        n_rows = sum(s.n_blank_rows + s.n_incomplete_rows for s in dropped)
        print(f"  无效行    : {len(dropped)} 个文件共 {n_rows} 行（末尾空行 / 截断行），已排除")
    else:
        print("  无效行    : 无")
    print(f"  无穷值    : {'无' if not bad_inf else f'{len(bad_inf)} 个文件存在 inf'}")
    print(f"  读取失败  : {'无' if not errored else f'{len(errored)} 个文件'}")
    if dropped:
        print("\n  含无效行的文件：")
        for s in dropped[:10]:
            detail = []
            if s.n_blank_rows:
                detail.append(f"空行 {s.n_blank_rows}")
            if s.n_incomplete_rows:
                detail.append(f"截断行 {s.n_incomplete_rows}")
            print(f"    {s.subject}/{s.name}  → {'，'.join(detail)}")
    if bad_header:
        print("\n  表头异常的文件：")
        for s in bad_header[:10]:
            print(f"    {s.subject}/{s.name}")
            print(f"      实际: {s.header_seen}")
    print()

    # ---- 3 时间轴 ----
    print(bar)
    print(" 3. 时间轴与采样率")
    print(bar)
    non_mono = [s for s in stats if not s.time_monotonic]
    dup = [s for s in stats if s.n_dup_time]
    print(f"  单调递增  : {'是，全部文件' if not non_mono else f'否，{len(non_mono)} 个文件时间倒流'}")
    print(f"  重复时间戳: {'无' if not dup else f'{len(dup)} 个文件存在重复'}")
    if agg["n_dt"]:
        print(f"\n  time 列相邻步长分布（毫秒，仅统计 ≤ {MAX_DT_MS} ms 的间隔）：")
        for step, cnt in sorted(agg["dt_hist"].items()):
            print(f"    {step:>2} ms : {cnt:>10,}  {pct(cnt, agg['n_dt'])}")
        gaps = sum(c for k, c in agg["dt_hist"].items() if k >= GAP_MS)
        print()
        print(f"  平均步长  : {agg['mean_dt_ms']:.3f} ms")
        print(f"  推算采样率: {MS_PER_S / agg['mean_dt_ms']:.0f} Hz")
        print(f"  时间缺口  : {gaps:,} 处（步长 ≥ {GAP_MS} ms，占 {pct(gaps, agg['n_dt'])}）")
    print()

    # ---- 4 类别 ----
    print(bar)
    print(" 4. 类别分布（全局）")
    print(bar)
    total = sum(agg["class_counts"].values())
    for label in sorted(agg["class_counts"]):
        name = CLASS_NAMES.get(label, "未知")
        cnt = agg["class_counts"][label]
        print(f"  class {label}  {name:<5} {cnt:>10,}  {pct(cnt, total)}")
    print(f"  {'合计':<12} {total:>10,}")
    print()

    # ---- 5 受试者 × 类别 ----
    print(bar)
    print(" 5. 受试者 × 类别")
    print(bar)
    all_labels = sorted(agg["class_counts"])
    groups: dict = {}
    for sub, labels in agg["per_subject"].items():
        groups.setdefault(frozenset(labels), []).append(sub)
    for labelset, who in sorted(groups.items(), key=lambda kv: -len(kv[0])):
        missing = [str(x) for x in all_labels if x not in labelset]
        desc = f"类别 {min(labelset)}–{max(labelset)}"
        tail = f"（缺 class {'、'.join(missing)}）" if missing else ""
        print(f"  {desc}  共 {len(who)} 人 {tail}")
        print(f"    {' '.join(sorted(who))}")
    print()

    # ---- 6 异常 ----
    print(bar)
    print(" 6. 异常与提示")
    print(bar)
    issues = list(warnings)
    for s in errored[:5]:
        issues.append(f"读取失败 {s.subject}/{s.name}：{s.error}")
    if dropped:
        n_rows = sum(s.n_blank_rows + s.n_incomplete_rows for s in dropped)
        names = "、".join(f"{s.subject}/{s.name}" for s in dropped[:5])
        issues.append(
            f"{len(dropped)} 个文件存在无效行（共 {n_rows} 行，本次已排除）：{names}"
            "。后续脚本读取时也必须丢弃这类行，否则会产生无标签样本"
        )
    if bad_width:
        issues.append(f"{len(bad_width)} 个文件列数不是 {len(EXPECTED_COLUMNS)}")
    if non_mono:
        issues.append(f"{len(non_mono)} 个文件时间列非单调递增")
    if dup:
        issues.append(f"{len(dup)} 个文件存在重复时间戳")
    if total:
        dominant, dom_cnt = agg["class_counts"].most_common(1)[0]
        frac = dom_cnt / total
        if frac > 0.5:
            issues.append(f"类别 {dominant}（{CLASS_NAMES.get(dominant, '?')}）占 {frac:.1%}，训练前需处理不平衡")
        sparse = [l for l, c in agg["class_counts"].items() if c < 0.01 * total]
        if sparse:
            issues.append("样本极少的类别：" + "、".join(f"class {l}（{agg['class_counts'][l]:,} 条）" for l in sorted(sparse)))
    rare = [s for s, v in agg["per_subject"].items() if len(v) < len(all_labels)]
    if 0 < len(rare) < agg["n_subjects"]:
        issues.append(f"{len(rare)} 名受试者未覆盖全部 {len(all_labels)} 个类别，跨受试者划分时需注意")

    if issues:
        for i, msg in enumerate(issues, 1):
            print(f"  {i}. {msg}")
    else:
        print("  未发现异常。")
    print()


# ---------------------------------------------------------------- 入口


def find_files(data_dir: Path):
    """返回 (文件列表, 警告列表)。"""
    warnings = []
    if not data_dir.is_dir():
        raise SystemExit(f"错误：数据目录不存在 -> {data_dir}")

    subject_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    if not subject_dirs:
        raise SystemExit(f"错误：{data_dir} 下没有受试者子目录")

    files = []
    for sub in subject_dirs:
        if not SUBJECT_RE.match(sub.name):
            warnings.append(f"目录名不符合两位数约定，已跳过：{sub.name}")
            continue
        found = sorted(p for p in sub.iterdir() if p.is_file() and p.suffix == ".txt")
        if not found:
            warnings.append(f"受试者 {sub.name} 下没有 .txt 文件")
        files.extend(found)

    stray = [p.name for p in data_dir.iterdir() if p.is_file()]
    if stray:
        warnings.append("data/ 根目录下有散落文件：" + "、".join(stray))

    return files, warnings


def build_json(stats: list, agg: dict, warnings: list) -> dict:
    return {
        "summary": {
            "n_files": agg["n_files"],
            "n_subjects": agg["n_subjects"],
            "total_rows": agg["total_rows"],
            "total_bytes": agg["total_bytes"],
            "mean_dt_ms": agg["mean_dt_ms"],
            "estimated_fs_hz": MS_PER_S / agg["mean_dt_ms"] if agg["mean_dt_ms"] else None,
        },
        "class_counts": {str(k): v for k, v in sorted(agg["class_counts"].items())},
        "dt_hist": {str(k): v for k, v in sorted(agg["dt_hist"].items())},
        "per_subject_classes": {s: sorted(v) for s, v in sorted(agg["per_subject"].items())},
        "files": [
            {
                "subject": s.subject,
                "name": s.name,
                "size_bytes": s.size_bytes,
                "n_rows": s.n_rows,
                "n_cols": s.n_cols,
                "header_ok": s.header_ok,
                "n_blank_rows": s.n_blank_rows,
                "n_incomplete_rows": s.n_incomplete_rows,
                "n_inf": s.n_inf,
                "time_monotonic": s.time_monotonic,
                "n_dup_time": s.n_dup_time,
                "mean_dt_ms": s.mean_dt_ms,
                "duration_ms": s.duration_ms,
                "class_counts": {str(k): v for k, v in sorted(s.class_counts.items())},
                "error": s.error,
            }
            for s in stats
        ],
        "warnings": warnings,
    }


def main() -> None:
    # Windows 控制台默认 GBK，中文报告会乱码，强制按 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="原始 sEMG 数据集体检（只读）")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
        help="数据目录，默认为仓库根下的 data/",
    )
    parser.add_argument("--json", type=Path, help="把汇总写入指定 JSON 文件")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    files, warnings = find_files(data_dir)

    print(f"正在体检 {len(files)} 个文件 ……\n")
    stats = [inspect_file(p) for p in files]
    agg = collect(stats)
    print_report(stats, agg, data_dir, warnings)

    if args.json:
        args.json.write_text(
            json.dumps(build_json(stats, agg, warnings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"汇总已写入 {args.json}")


if __name__ == "__main__":
    main()
