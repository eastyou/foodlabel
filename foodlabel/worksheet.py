"""营养成分表练习纸生成：读标签算每份、算 NRV%、判断能量高低。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from html import escape
from typing import List, Optional, Sequence

from .nutrition import (
    NRV_VALUES,
    NUTRIENT_KEYS,
    NUTRIENT_LABELS,
    NUTRIENT_UNITS,
    Label,
    energy_level,
    format_amount,
    format_percent,
    nrv_percent,
    read_label,
)

MAX_QUESTIONS: int = 100

KIND_SERVING: str = "读标签算每份"
KIND_NRV: str = "算 NRV%"
KIND_LEVEL: str = "判断能量高低"

_KINDS: List[str] = [KIND_SERVING, KIND_NRV, KIND_LEVEL]

# 名称、每 100 g 的能量 kJ、蛋白质 g、脂肪 g、碳水化合物 g、钠 mg
_FOOD_TABLE = (
    ("全麦面包", 1050.0, 8.0, 5.0, 49.0, 300.0),
    ("纯牛奶", 270.0, 3.0, 3.0, 5.0, 50.0),
    ("原味酸奶", 400.0, 3.5, 3.0, 12.0, 60.0),
    ("巧克力饼干", 2100.0, 6.0, 24.0, 62.0, 280.0),
    ("苏打饼干", 1670.0, 8.0, 12.0, 68.0, 500.0),
    ("苹果", 218.0, 0.3, 0.2, 13.5, 2.0),
    ("香蕉", 372.0, 1.4, 0.2, 22.0, 1.0),
    ("方便面", 1900.0, 9.5, 20.0, 61.0, 2100.0),
    ("番茄汁", 84.0, 0.8, 0.2, 4.0, 120.0),
    ("鸡蛋", 602.0, 13.3, 8.8, 2.8, 131.0),
)

_SERVINGS = (20.0, 25.0, 30.0, 40.0, 50.0, 100.0)

_STYLE = """
body { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; margin: 32px auto; max-width: 780px; color: #222; line-height: 1.7; }
h1 { font-size: 22px; border-bottom: 2px solid #4a6fa5; padding-bottom: 8px; }
.meta { color: #666; font-size: 14px; }
ol { padding-left: 24px; }
li { margin-bottom: 18px; }
details { margin-top: 6px; color: #1f5f3f; }
summary { cursor: pointer; color: #4a6fa5; }
"""


@dataclass(frozen=True)
class WorksheetItem:
    """练习纸上的一道题。"""

    kind: str
    question: str
    answer: str


def _default_labels() -> List[Label]:
    labels: List[Label] = []
    for name, energy, protein, fat, carbs, sodium in _FOOD_TABLE:
        labels.append(
            read_label(energy, protein, fat, carbs, sodium, name=name)
        )
    return labels


def _serving_item(rng: random.Random, label: Label) -> WorksheetItem:
    serving = label.serving if label.serving is not None else rng.choice(_SERVINGS)
    energy = label.per_100.energy_kj
    per_serving_kj = energy * serving / 100.0
    per_serving_kcal = per_serving_kj / 4.184
    question = "{0}每 100 g 含能量 {1} kJ，一份（{2} g）提供多少能量？".format(
        label.name, format_amount(energy), format_amount(serving)
    )
    answer = "{0} × {1} ÷ 100 = {2} kJ，约 {3:.1f} kcal。".format(
        format_amount(energy),
        format_amount(serving),
        format_amount(per_serving_kj),
        per_serving_kcal,
    )
    return WorksheetItem(kind=KIND_SERVING, question=question, answer=answer)


def _nrv_item(rng: random.Random, label: Label) -> WorksheetItem:
    nutrient = rng.choice(NUTRIENT_KEYS)
    value = label.per_100.amount(nutrient)
    nrv_value = NRV_VALUES[nutrient]
    unit = NUTRIENT_UNITS[nutrient]
    percent = nrv_percent(nutrient, value)
    question = "{0}每 100 g 含{1} {2} {3}，{1}的 NRV 为 {4} {3}，它的 NRV% 是多少？".format(
        label.name,
        NUTRIENT_LABELS[nutrient],
        format_amount(value),
        unit,
        format_amount(nrv_value),
    )
    answer = "NRV% = {0} ÷ {1} × 100% = {2}%。".format(
        format_amount(value), format_amount(nrv_value), format_percent(percent)
    )
    return WorksheetItem(kind=KIND_NRV, question=question, answer=answer)


def _level_item(label: Label) -> WorksheetItem:
    energy = label.per_100.energy_kj
    level = energy_level(energy)
    question = (
        "{0}每 100 g 能量为 {1} kJ，按教学参考属于低能量、中等能量还是高能量？"
    ).format(label.name, format_amount(energy))
    answer = (
        "{0}。教学参考：每 100 g 能量低于 400 kJ 为低能量，"
        "400 到 1670 kJ 为中等能量，高于 1670 kJ 为高能量。"
    ).format(level)
    return WorksheetItem(kind=KIND_LEVEL, question=question, answer=answer)


def _build_items(
    count: int, rng: random.Random, labels: Sequence[Label]
) -> List[WorksheetItem]:
    items: List[WorksheetItem] = []
    for index in range(count):
        kind = _KINDS[index % len(_KINDS)]
        label = labels[rng.randrange(len(labels))]
        if kind == KIND_SERVING:
            items.append(_serving_item(rng, label))
        elif kind == KIND_NRV:
            items.append(_nrv_item(rng, label))
        else:
            items.append(_level_item(label))
    return items


def generate_worksheet(
    count: int = 10,
    seed: Optional[int] = None,
    labels: Optional[Sequence[Label]] = None,
) -> str:
    """生成包含三类题型的 HTML 练习纸，答案放在可折叠的 ``<details>`` 中。

    ``count`` 必须在 1 到 100 之间；相同 ``seed`` 会生成相同题目。
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("题目数量必须是整数")
    if count < 1 or count > MAX_QUESTIONS:
        raise ValueError("题目数量必须在 1 到 %d 之间" % MAX_QUESTIONS)
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError("随机种子必须是整数")

    pool: List[Label]
    if labels is None:
        pool = _default_labels()
    else:
        pool = list(labels)
        if not pool:
            raise ValueError("自定义标签列表不能为空")
        for label in pool:
            if not isinstance(label, Label):
                raise TypeError("自定义标签必须是 Label 对象")

    rng = random.Random(seed)
    items = _build_items(count, rng, pool)

    lines: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>营养成分表练习纸</title>",
        "<style>%s</style>" % _STYLE,
        "</head>",
        "<body>",
        "<h1>营养成分表练习纸</h1>",
        '<p class="meta">题目数量：%d</p>' % len(items),
        "<ol>",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(
            "<li>第 %d 题【%s】%s"
            % (index, escape(item.kind), escape(item.question))
        )
        lines.append(
            "<details><summary>查看答案</summary><p>答案：%s</p></details>"
            % escape(item.answer)
        )
        lines.append("</li>")
    lines.extend(["</ol>", "</body>", "</html>"])
    return "\n".join(lines) + "\n"
