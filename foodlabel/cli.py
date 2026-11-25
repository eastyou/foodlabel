"""foodlabel 命令行入口：读取营养标签、计算 NRV、对比食品与生成练习纸。"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from typing import List, Optional, Sequence

from .nutrition import (
    KJ_PER_KCAL,
    NRV_VALUES,
    NUTRIENT_KEYS,
    NUTRIENT_LABELS,
    NUTRIENT_UNITS,
    Comparison,
    Label,
    compare_labels,
    energy_level,
    format_amount,
    format_percent,
    nrv_percent,
    read_label,
)
from .worksheet import MAX_QUESTIONS, generate_worksheet


def _ensure_utf8_console() -> None:
    """尽量把标准输出与标准错误切换为 UTF-8，失败时静默跳过。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            continue


def _display_width(text: str) -> int:
    """按终端显示宽度计算字符串长度，宽字符（中文）按 2 计。"""
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _pad(text: str, width: int) -> str:
    padding = width - _display_width(text)
    if padding <= 0:
        return text
    return text + " " * padding


def _render_table(headers: List[str], rows: List[List[str]]) -> str:
    """把二维文本排成带分隔线的简单表格。"""
    column_count = len(headers)
    widths = [_display_width(header) for header in headers]
    for row in rows:
        for index in range(column_count):
            widths[index] = max(widths[index], _display_width(row[index]))

    lines: List[str] = []
    lines.append(
        "  ".join(_pad(headers[index], widths[index]) for index in range(column_count)).rstrip()
    )
    lines.append("  ".join("-" * widths[index] for index in range(column_count)))
    for row in rows:
        lines.append(
            "  ".join(_pad(row[index], widths[index]) for index in range(column_count)).rstrip()
        )
    return "\n".join(lines)


def _amount_cell(nutrient: str, value: float) -> str:
    unit = NUTRIENT_UNITS[nutrient]
    if nutrient == "energy":
        return "%s kJ（%.1f kcal）" % (format_amount(value), value / KJ_PER_KCAL)
    return "%s %s" % (format_amount(value), unit)


def _signed(value: float) -> str:
    if abs(value) < 1e-9:
        return "0"
    sign = "+" if value > 0 else "-"
    return sign + format_amount(abs(value))


def _format_label_report(label: Label) -> str:
    """生成一张标签的解读文本（每 100 g、每份与 NRV%）。"""
    per_100 = label.per_100
    per_serving = label.per_serving
    headers = ["营养素", "每 100 g"]
    if per_serving is not None and label.serving is not None:
        headers.append("每份（%s g）" % format_amount(label.serving))
    headers.append("NRV%（每 100 g）")

    rows: List[List[str]] = []
    for nutrient in NUTRIENT_KEYS:
        value = per_100.amount(nutrient)
        cells = [NUTRIENT_LABELS[nutrient], _amount_cell(nutrient, value)]
        if per_serving is not None:
            cells.append(_amount_cell(nutrient, per_serving.amount(nutrient)))
        cells.append("%s%%" % format_percent(nrv_percent(nutrient, value)))
        rows.append(cells)

    lines: List[str] = ["食品：%s" % label.name, _render_table(headers, rows)]
    lines.append(
        "能量密度：%s（教学参考：每 100 g 低于 400 kJ 为低能量，"
        "400 到 1670 kJ 为中等能量，高于 1670 kJ 为高能量）"
        % energy_level(per_100.energy_kj)
    )
    return "\n".join(lines)


def _format_nrv_report(nutrient: str, value: float) -> str:
    """生成单项 NRV% 的计算过程。"""
    percent = nrv_percent(nutrient, value)
    unit = NUTRIENT_UNITS[nutrient]
    nrv_value = NRV_VALUES[nutrient]
    lines: List[str] = [
        "营养素：%s" % NUTRIENT_LABELS[nutrient],
        "含量：%s %s" % (format_amount(value), unit),
        "NRV 参考值：%s %s" % (format_amount(nrv_value), unit),
        "NRV%% = %s ÷ %s × 100%% = %s%%"
        % (format_amount(value), format_amount(nrv_value), format_percent(percent)),
    ]
    return "\n".join(lines)


def _format_comparison_report(comparison: Comparison) -> str:
    """生成两张标签的差值表与 NRV% 对比。"""
    first = comparison.first
    second = comparison.second
    headers = [
        "营养素",
        "%s（每 100 g）" % first.name,
        "%s（每 100 g）" % second.name,
        "差值（%s - %s）" % (first.name, second.name),
        "NRV% 对比",
    ]
    rows: List[List[str]] = []
    for row in comparison.rows:
        unit = NUTRIENT_UNITS[row.nutrient]
        higher = comparison.higher_name(row)
        if higher == "相同":
            nrv_text = "%s%% vs %s%%（相同）" % (
                format_percent(row.nrv_a),
                format_percent(row.nrv_b),
            )
        else:
            nrv_text = "%s%% vs %s%%（%s更高）" % (
                format_percent(row.nrv_a),
                format_percent(row.nrv_b),
                higher,
            )
        rows.append(
            [
                NUTRIENT_LABELS[row.nutrient],
                "%s %s" % (format_amount(row.value_a), unit),
                "%s %s" % (format_amount(row.value_b), unit),
                "%s %s" % (_signed(row.difference), unit),
                nrv_text,
            ]
        )
    lines: List[str] = [
        "对比（每 100 g）：%s vs %s" % (first.name, second.name),
        _render_table(headers, rows),
    ]
    return "\n".join(lines)


def _parse_label_spec(text: str) -> Label:
    """解析“名称:能量:蛋白质:脂肪:碳水:钠”形式的标签字符串。"""
    parts = [item.strip() for item in text.split(":")]
    if len(parts) != 6:
        raise ValueError(
            "标签格式应为“名称:能量:蛋白质:脂肪:碳水:钠”，实际得到 %d 段：%s"
            % (len(parts), text)
        )
    fields = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
    values: List[float] = []
    for index, field in enumerate(fields):
        chunk = parts[index + 1]
        try:
            values.append(float(chunk))
        except (TypeError, ValueError) as exc:
            raise ValueError("%s 不是数字：%s" % (field, chunk)) from exc
    return read_label(
        values[0], values[1], values[2], values[3], values[4], name=parts[0]
    )


def _number_argument(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("无法把 %s 解析为数字" % text) from exc


def _count_argument(text: str) -> int:
    try:
        value = int(text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("题目数量必须是整数：%s" % text) from exc
    if value < 1 or value > MAX_QUESTIONS:
        raise argparse.ArgumentTypeError(
            "题目数量必须在 1 到 %d 之间" % MAX_QUESTIONS
        )
    return value


def _seed_argument(text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("随机种子必须是整数：%s" % text) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foodlabel",
        description="营养成分表解读工具：每份换算、NRV 占比、能量分级与练习纸",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    read_parser = subparsers.add_parser(
        "read", help="读一张标签：每 100 g、每份与 NRV%%"
    )
    read_parser.add_argument(
        "--energy", required=True, type=_number_argument, help="每 100 g 能量（kJ）"
    )
    read_parser.add_argument(
        "--protein", required=True, type=_number_argument, help="每 100 g 蛋白质（g）"
    )
    read_parser.add_argument(
        "--fat", required=True, type=_number_argument, help="每 100 g 脂肪（g）"
    )
    read_parser.add_argument(
        "--carbs", required=True, type=_number_argument, help="每 100 g 碳水化合物（g）"
    )
    read_parser.add_argument(
        "--sodium", required=True, type=_number_argument, help="每 100 g 钠（mg）"
    )
    read_parser.add_argument(
        "--serving", type=_number_argument, default=None, help="每份质量（g），可选"
    )

    nrv_parser = subparsers.add_parser("nrv", help="计算单项 NRV%%")
    nrv_parser.add_argument(
        "--nutrient",
        required=True,
        help="营养素：energy、protein、fat、carbs、sodium",
    )
    nrv_parser.add_argument(
        "--value",
        required=True,
        type=_number_argument,
        help="每 100 g 含量（能量用 kJ，钠用 mg，其余用 g）",
    )

    compare_parser = subparsers.add_parser(
        "compare", help="对比两张标签的每 100 g 含量与 NRV%%"
    )
    compare_parser.add_argument(
        "--a",
        required=True,
        help="第一张标签：名称:能量:蛋白质:脂肪:碳水:钠",
    )
    compare_parser.add_argument(
        "--b",
        required=True,
        help="第二张标签：名称:能量:蛋白质:脂肪:碳水:钠",
    )

    worksheet_parser = subparsers.add_parser("worksheet", help="生成 HTML 练习纸")
    worksheet_parser.add_argument(
        "--count",
        type=_count_argument,
        default=8,
        help="题目数量，1 到 %d，默认 8" % MAX_QUESTIONS,
    )
    worksheet_parser.add_argument(
        "--seed", type=_seed_argument, default=2026, help="随机种子，默认 2026"
    )
    worksheet_parser.add_argument("--out", required=True, help="输出 HTML 文件路径")

    subparsers.add_parser(
        "demo", help="打印示例：标签解读、两条 NRV 计算与一组对比"
    )
    return parser


def _write_text(path: str, content: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as exc:
        raise ValueError("写入文件失败：{0}（{1}）".format(path, exc.strerror or exc)) from exc


def _read_command(args: argparse.Namespace) -> int:
    label = read_label(
        args.energy,
        args.protein,
        args.fat,
        args.carbs,
        args.sodium,
        serving=args.serving,
    )
    print(_format_label_report(label))
    return 0


def _nrv_command(args: argparse.Namespace) -> int:
    print(_format_nrv_report(args.nutrient, args.value))
    return 0


def _compare_command(args: argparse.Namespace) -> int:
    first = _parse_label_spec(args.a)
    second = _parse_label_spec(args.b)
    print(_format_comparison_report(compare_labels(first, second)))
    return 0


def _worksheet_command(args: argparse.Namespace) -> int:
    html_text = generate_worksheet(args.count, args.seed)
    _write_text(args.out, html_text)
    print("已写入 %s（共 %d 题）" % (args.out, args.count))
    return 0


def _demo_command() -> int:
    label = read_label(
        1050.0, 8.0, 12.0, 45.0, 400.0, serving=25.0, name="示例饼干"
    )
    print("一、标签解读")
    print(_format_label_report(label))
    print("")
    print("二、NRV 计算")
    print(_format_nrv_report("energy", 1050.0))
    print("")
    print(_format_nrv_report("protein", 8.0))
    print("")
    print("三、食品对比")
    first = read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="面包")
    second = read_label(270.0, 3.0, 3.0, 5.0, 50.0, name="牛奶")
    print(_format_comparison_report(compare_labels(first, second)))
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "read":
        return _read_command(args)
    if args.command == "nrv":
        return _nrv_command(args)
    if args.command == "compare":
        return _compare_command(args)
    if args.command == "worksheet":
        return _worksheet_command(args)
    if args.command == "demo":
        return _demo_command()
    raise ValueError("未知子命令：%s" % args.command)


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ensure_utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (TypeError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
