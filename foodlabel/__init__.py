"""foodlabel：营养成分表解读工具。

提供每份换算、NRV 占比、能量分级、标签对比与 HTML 练习纸生成。
"""

from __future__ import annotations

from .nutrition import (
    Label,
    Nutrition,
    compare_labels,
    energy_level,
    nrv_percent,
    read_label,
)
from .worksheet import generate_worksheet

__version__ = "0.1.0"

__all__ = [
    "Label",
    "Nutrition",
    "compare_labels",
    "energy_level",
    "generate_worksheet",
    "nrv_percent",
    "read_label",
]
