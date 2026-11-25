"""营养成分表计算：每份换算、NRV 占比、能量分级与标签对比。

所有含量均按每 100 g（或 100 mL）计：能量单位 kJ，蛋白质、脂肪、碳水化合物
单位 g，钠单位 mg。换算每份时按 ``每份质量 / 100`` 等比缩放。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, Optional, Tuple

KJ_PER_KCAL: float = 4.184
MAX_NUTRIENT: float = 1e6
MAX_SERVING: float = 5000.0
LOW_ENERGY_MAX: float = 400.0
HIGH_ENERGY_MIN: float = 1670.0

NUTRIENT_KEYS: Tuple[str, ...] = ("energy", "protein", "fat", "carbs", "sodium")

NUTRIENT_LABELS: Dict[str, str] = {
    "energy": "能量",
    "protein": "蛋白质",
    "fat": "脂肪",
    "carbs": "碳水化合物",
    "sodium": "钠",
}

NUTRIENT_UNITS: Dict[str, str] = {
    "energy": "kJ",
    "protein": "g",
    "fat": "g",
    "carbs": "g",
    "sodium": "mg",
}

# 中国预包装食品营养标签通则的教学简化值
NRV_VALUES: Dict[str, float] = {
    "energy": 8400.0,
    "protein": 60.0,
    "fat": 60.0,
    "carbs": 300.0,
    "sodium": 2000.0,
}


def _number(value: Any, name: str, maximum: float = MAX_NUTRIENT) -> float:
    """校验并转换数值：拒绝 bool、非数字、NaN/inf、负数与超上限值。"""
    if isinstance(value, bool):
        raise ValueError("%s 不能是布尔值" % name)
    if not isinstance(value, (int, float)):
        raise ValueError("%s 必须是数字" % name)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s 必须是有限数字（不能是 NaN 或无穷大）" % name)
    if number < 0:
        raise ValueError("%s 不能为负数" % name)
    if number > maximum:
        raise ValueError("%s 不能大于 %s" % (name, maximum))
    return number


def _nutrient_key(nutrient: str) -> str:
    """确认营养素名称合法，未知时抛出列出可选值的中文错误。"""
    if nutrient not in NRV_VALUES:
        raise ValueError(
            "未知营养素：%s（可选：%s）" % (nutrient, "、".join(NUTRIENT_KEYS))
        )
    return nutrient


def _round1(value: float) -> float:
    """四舍五入到 1 位小数。"""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def format_amount(value: float) -> str:
    """把数值格式化为最多 1 位小数，整数去掉小数点。"""
    rounded = _round1(float(value))
    if rounded == int(rounded):
        return str(int(rounded))
    return "%.1f" % rounded


def format_percent(value: float) -> str:
    """把 NRV% 格式化为保留 1 位小数的字符串（不含百分号）。"""
    return "%.1f" % _round1(float(value))


@dataclass(frozen=True)
class Nutrition:
    """一组营养素含量（每 100 g 或每份），单位见 :data:`NUTRIENT_UNITS`。"""

    energy_kj: float
    protein: float
    fat: float
    carbs: float
    sodium: float

    @property
    def energy_kcal(self) -> float:
        """能量换算成千卡（1 kcal = 4.184 kJ）。"""
        return self.energy_kj / KJ_PER_KCAL

    def amount(self, nutrient: str) -> float:
        """按营养素名称取含量，未知时抛出 ValueError。"""
        key = _nutrient_key(nutrient)
        if key == "energy":
            return self.energy_kj
        if key == "protein":
            return self.protein
        if key == "fat":
            return self.fat
        if key == "carbs":
            return self.carbs
        return self.sodium

    def scaled(self, factor: float) -> "Nutrition":
        """按比例缩放全部营养素。"""
        return Nutrition(
            energy_kj=self.energy_kj * factor,
            protein=self.protein * factor,
            fat=self.fat * factor,
            carbs=self.carbs * factor,
            sodium=self.sodium * factor,
        )


@dataclass(frozen=True)
class Label:
    """一张营养成分表：食品名称、每 100 g 含量与可选的每份质量（g）。"""

    name: str
    per_100: Nutrition
    serving: Optional[float] = None

    @property
    def per_serving(self) -> Optional[Nutrition]:
        """每份含量，未提供每份质量时返回 None。"""
        if self.serving is None:
            return None
        return self.per_100.scaled(self.serving / 100.0)


@dataclass(frozen=True)
class ComparisonRow:
    """单个营养素的两张标签对比结果（每 100 g）。"""

    nutrient: str
    value_a: float
    value_b: float
    nrv_a: float
    nrv_b: float

    @property
    def difference(self) -> float:
        """第一张标签减去第二张标签的含量差。"""
        return self.value_a - self.value_b


@dataclass(frozen=True)
class Comparison:
    """两张标签的对比结果。"""

    first: Label
    second: Label
    rows: Tuple[ComparisonRow, ...]

    def higher_name(self, row: ComparisonRow) -> str:
        """返回 NRV% 更高的一方名称，相同时返回“相同”。"""
        if row.nrv_a == row.nrv_b:
            return "相同"
        return self.first.name if row.nrv_a > row.nrv_b else self.second.name


def read_label(
    energy_kj: float,
    protein: float,
    fat: float,
    carbs: float,
    sodium: float,
    serving: Optional[float] = None,
    name: str = "样品",
) -> Label:
    """校验每 100 g 数值并构建 :class:`Label`。

    所有数值必须为 0 到 1e6 之间的有限数；``serving`` 若给出必须
    在 0（不含）到 5000 之间。
    """
    if not isinstance(name, str):
        raise ValueError("名称必须是字符串")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("名称不能为空")

    per_100 = Nutrition(
        energy_kj=_number(energy_kj, "能量"),
        protein=_number(protein, "蛋白质"),
        fat=_number(fat, "脂肪"),
        carbs=_number(carbs, "碳水化合物"),
        sodium=_number(sodium, "钠"),
    )

    serving_value: Optional[float] = None
    if serving is not None:
        serving_value = _number(serving, "每份质量", MAX_SERVING)
        if serving_value <= 0:
            raise ValueError("每份质量必须大于 0")

    return Label(name=clean_name, per_100=per_100, serving=serving_value)


def nrv_percent(nutrient: str, value: float) -> float:
    """计算营养素参考值百分比，保留 1 位小数。

    能量按 kJ 与 8400 kJ 相比，蛋白质/脂肪按 g 与 60 g 相比，
    碳水化合物按 g 与 300 g 相比，钠按 mg 与 2000 mg 相比。
    """
    key = _nutrient_key(nutrient)
    amount = _number(value, "含量")
    return _round1(amount / NRV_VALUES[key] * 100.0)


def energy_level(energy_kj: float) -> str:
    """按每 100 g 能量给出教学用分级：低能量、中等能量或高能量。"""
    value = _number(energy_kj, "能量")
    if value < LOW_ENERGY_MAX:
        return "低能量"
    if value <= HIGH_ENERGY_MIN:
        return "中等能量"
    return "高能量"


def compare_labels(first: Label, second: Label) -> Comparison:
    """对比两张标签每 100 g 的含量差与 NRV%，返回 :class:`Comparison`。"""
    if not isinstance(first, Label) or not isinstance(second, Label):
        raise TypeError("compare_labels 需要两个 Label 对象")

    rows = []
    for nutrient in NUTRIENT_KEYS:
        value_a = first.per_100.amount(nutrient)
        value_b = second.per_100.amount(nutrient)
        rows.append(
            ComparisonRow(
                nutrient=nutrient,
                value_a=value_a,
                value_b=value_b,
                nrv_a=nrv_percent(nutrient, value_a),
                nrv_b=nrv_percent(nutrient, value_b),
            )
        )
    return Comparison(first=first, second=second, rows=tuple(rows))
