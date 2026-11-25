"""foodlabel 单元测试。"""

from __future__ import annotations

import io
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from html import escape
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from foodlabel import (  # noqa: E402
    Label,
    Nutrition,
    compare_labels,
    energy_level,
    generate_worksheet,
    nrv_percent,
    read_label,
)
from foodlabel import cli  # noqa: E402
from foodlabel.nutrition import (  # noqa: E402
    NRV_VALUES,
    format_amount,
    format_percent,
)
from foodlabel.worksheet import MAX_QUESTIONS  # noqa: E402


def _run_cli(argv: List[str]) -> Tuple[int, str, str]:
    """运行 CLI 并捕获标准输出、标准错误与退出码。"""
    out = io.StringIO()
    err = io.StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = int(exc.code) if exc.code is not None else 0
    return code, out.getvalue(), err.getvalue()


def _sample_label(serving: Optional[float] = None) -> Label:
    """1050 kJ / 8 g 蛋白质 / 12 g 脂肪 / 45 g 碳水 / 400 mg 钠。"""
    return read_label(
        1050.0, 8.0, 12.0, 45.0, 400.0, serving=serving, name="示例饼干"
    )


class TestValidation(unittest.TestCase):
    def test_negative_values_rejected(self) -> None:
        for field in ("energy_kj", "protein", "fat", "carbs", "sodium"):
            values = {
                "energy_kj": 1050.0,
                "protein": 8.0,
                "fat": 12.0,
                "carbs": 45.0,
                "sodium": 400.0,
            }
            values[field] = -1.0
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    read_label(
                        values["energy_kj"],
                        values["protein"],
                        values["fat"],
                        values["carbs"],
                        values["sodium"],
                    )

    def test_value_above_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(1e6 + 1, 8.0, 12.0, 45.0, 400.0)

    def test_nan_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(float("nan"), 8.0, 12.0, 45.0, 400.0)

    def test_infinity_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(float("inf"), 8.0, 12.0, 45.0, 400.0)

    def test_bool_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(True, 8.0, 12.0, 45.0, 400.0)

    def test_string_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label("1050", 8.0, 12.0, 45.0, 400.0)

    def test_serving_zero_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _sample_label(serving=0.0)

    def test_serving_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _sample_label(serving=-5.0)

    def test_serving_above_limit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _sample_label(serving=5001.0)

    def test_serving_at_limit_accepted(self) -> None:
        label = _sample_label(serving=5000.0)
        self.assertEqual(label.serving, 5000.0)

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="   ")

    def test_non_string_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name=123)

    def test_name_is_stripped(self) -> None:
        label = read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="  面包  ")
        self.assertEqual(label.name, "面包")


class TestPerServing(unittest.TestCase):
    def test_energy_per_serving(self) -> None:
        label = _sample_label(serving=25.0)
        self.assertIsNotNone(label.per_serving)
        self.assertAlmostEqual(label.per_serving.energy_kj, 262.5, places=6)

    def test_macros_per_serving(self) -> None:
        label = _sample_label(serving=25.0)
        per_serving = label.per_serving
        self.assertIsNotNone(per_serving)
        self.assertAlmostEqual(per_serving.protein, 2.0, places=6)
        self.assertAlmostEqual(per_serving.fat, 3.0, places=6)
        self.assertAlmostEqual(per_serving.carbs, 11.25, places=6)
        self.assertAlmostEqual(per_serving.sodium, 100.0, places=6)

    def test_no_serving_returns_none(self) -> None:
        self.assertIsNone(_sample_label().per_serving)

    def test_serving_100_equals_per_100(self) -> None:
        label = _sample_label(serving=100.0)
        per_serving = label.per_serving
        self.assertIsNotNone(per_serving)
        self.assertAlmostEqual(per_serving.energy_kj, label.per_100.energy_kj)

    def test_energy_kcal_per_100(self) -> None:
        label = _sample_label()
        self.assertAlmostEqual(
            label.per_100.energy_kcal, 1050.0 / 4.184, places=6
        )

    def test_energy_kcal_per_serving(self) -> None:
        label = _sample_label(serving=25.0)
        per_serving = label.per_serving
        self.assertIsNotNone(per_serving)
        self.assertAlmostEqual(per_serving.energy_kcal, 62.739, places=3)

    def test_scaled_proportional(self) -> None:
        nutrition = _sample_label().per_100
        doubled = nutrition.scaled(2.0)
        self.assertAlmostEqual(doubled.energy_kj, 2100.0)
        self.assertAlmostEqual(doubled.sodium, 800.0)

    def test_amount_lookup(self) -> None:
        nutrition = _sample_label().per_100
        self.assertEqual(nutrition.amount("fat"), 12.0)
        self.assertEqual(nutrition.amount("sodium"), 400.0)
        with self.assertRaises(ValueError):
            nutrition.amount("sugar")


class TestNrvPercent(unittest.TestCase):
    def test_energy_nrv(self) -> None:
        self.assertEqual(nrv_percent("energy", 1050.0), 12.5)

    def test_protein_nrv(self) -> None:
        self.assertEqual(nrv_percent("protein", 12.0), 20.0)

    def test_fat_nrv(self) -> None:
        self.assertEqual(nrv_percent("fat", 30.0), 50.0)

    def test_carbs_nrv(self) -> None:
        self.assertEqual(nrv_percent("carbs", 45.0), 15.0)

    def test_sodium_nrv(self) -> None:
        self.assertEqual(nrv_percent("sodium", 400.0), 20.0)

    def test_rounding_one_decimal(self) -> None:
        self.assertEqual(nrv_percent("protein", 1.0), 1.7)

    def test_unknown_nutrient_rejected(self) -> None:
        with self.assertRaises(ValueError):
            nrv_percent("sugar", 10.0)

    def test_unknown_nutrient_lists_options(self) -> None:
        with self.assertRaises(ValueError) as context:
            nrv_percent("sugar", 10.0)
        message = str(context.exception)
        self.assertIn("protein", message)
        self.assertIn("sodium", message)

    def test_negative_value_rejected(self) -> None:
        with self.assertRaises(ValueError):
            nrv_percent("energy", -1.0)

    def test_nan_value_rejected(self) -> None:
        with self.assertRaises(ValueError):
            nrv_percent("energy", float("nan"))

    def test_over_limit_value_rejected(self) -> None:
        with self.assertRaises(ValueError):
            nrv_percent("sodium", 1e6 + 1)


class TestEnergyLevel(unittest.TestCase):
    def test_zero_is_low(self) -> None:
        self.assertEqual(energy_level(0.0), "低能量")

    def test_just_below_boundary_is_low(self) -> None:
        self.assertEqual(energy_level(399.9), "低能量")

    def test_lower_boundary_is_medium(self) -> None:
        self.assertEqual(energy_level(400.0), "中等能量")

    def test_middle_is_medium(self) -> None:
        self.assertEqual(energy_level(1000.0), "中等能量")

    def test_upper_boundary_is_medium(self) -> None:
        self.assertEqual(energy_level(1670.0), "中等能量")

    def test_just_above_boundary_is_high(self) -> None:
        self.assertEqual(energy_level(1670.1), "高能量")

    def test_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            energy_level(-10.0)


class TestCompareLabels(unittest.TestCase):
    def _pair(self) -> Tuple[Label, Label]:
        first = read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="面包")
        second = read_label(270.0, 3.0, 3.0, 5.0, 50.0, name="牛奶")
        return first, second

    def test_row_count_and_order(self) -> None:
        comparison = compare_labels(*self._pair())
        self.assertEqual(len(comparison.rows), 5)
        self.assertEqual(
            [row.nutrient for row in comparison.rows],
            ["energy", "protein", "fat", "carbs", "sodium"],
        )

    def test_energy_difference(self) -> None:
        comparison = compare_labels(*self._pair())
        self.assertAlmostEqual(comparison.rows[0].difference, 780.0)

    def test_other_differences(self) -> None:
        comparison = compare_labels(*self._pair())
        differences = [row.difference for row in comparison.rows]
        self.assertAlmostEqual(differences[1], 5.0)
        self.assertAlmostEqual(differences[2], 9.0)
        self.assertAlmostEqual(differences[3], 40.0)
        self.assertAlmostEqual(differences[4], 350.0)

    def test_nrv_values(self) -> None:
        comparison = compare_labels(*self._pair())
        self.assertEqual(comparison.rows[0].nrv_a, 12.5)
        self.assertEqual(comparison.rows[0].nrv_b, 3.2)

    def test_higher_name_is_first(self) -> None:
        comparison = compare_labels(*self._pair())
        self.assertEqual(comparison.higher_name(comparison.rows[0]), "面包")

    def test_higher_name_is_second(self) -> None:
        first, second = self._pair()
        comparison = compare_labels(second, first)
        self.assertEqual(comparison.higher_name(comparison.rows[0]), "面包")

    def test_equal_nrv_says_same(self) -> None:
        first = read_label(840.0, 6.0, 6.0, 30.0, 200.0, name="甲")
        second = read_label(840.0, 6.0, 6.0, 30.0, 200.0, name="乙")
        comparison = compare_labels(first, second)
        for row in comparison.rows:
            self.assertEqual(comparison.higher_name(row), "相同")

    def test_requires_label_objects(self) -> None:
        with self.assertRaises(TypeError):
            compare_labels(_sample_label(), "牛奶")

    def test_markup_names_escaped_in_worksheet(self) -> None:
        first = read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="面<包>")
        second = read_label(270.0, 3.0, 3.0, 5.0, 50.0, name="牛奶&豆奶")
        comparison = compare_labels(first, second)
        self.assertEqual(comparison.first.name, "面<包>")
        for label in (comparison.first, comparison.second):
            html_text = generate_worksheet(3, 11, labels=[label])
            self.assertIn(escape(label.name), html_text)
            self.assertNotIn(label.name, html_text)


class TestWorksheet(unittest.TestCase):
    def test_starts_with_doctype(self) -> None:
        self.assertTrue(generate_worksheet(8, 2026).startswith("<!DOCTYPE html>"))

    def test_has_title_and_style(self) -> None:
        html_text = generate_worksheet(8, 2026)
        self.assertIn("<title>", html_text)
        self.assertIn("<style>", html_text)

    def test_eight_questions(self) -> None:
        html_text = generate_worksheet(8, 2026)
        self.assertEqual(html_text.count("<details>"), 8)
        self.assertEqual(html_text.count("<li>"), 8)

    def test_answers_hidden_in_details(self) -> None:
        html_text = generate_worksheet(2, 2026)
        self.assertIn("<details><summary>查看答案</summary>", html_text)

    def test_same_seed_reproducible(self) -> None:
        self.assertEqual(generate_worksheet(6, 42), generate_worksheet(6, 42))

    def test_different_seed_changes_output(self) -> None:
        self.assertNotEqual(generate_worksheet(6, 1), generate_worksheet(6, 2))

    def test_three_kinds_present(self) -> None:
        html_text = generate_worksheet(9, 2026)
        self.assertIn("读标签算每份", html_text)
        self.assertIn("算 NRV%", html_text)
        self.assertIn("判断能量高低", html_text)

    def test_count_zero_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(0, 1)

    def test_count_negative_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(-3, 1)

    def test_count_too_large_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(MAX_QUESTIONS + 1, 1)

    def test_count_bool_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(True, 1)

    def test_count_float_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(8.0, 1)

    def test_seed_bool_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(3, True)

    def test_custom_name_escaped(self) -> None:
        label = read_label(1050.0, 8.0, 12.0, 45.0, 400.0, name="面<包>&牛奶")
        html_text = generate_worksheet(3, 5, labels=[label])
        self.assertIn("面&lt;包&gt;&amp;牛奶", html_text)
        self.assertNotIn("面<包>&牛奶", html_text)

    def test_empty_labels_rejected(self) -> None:
        with self.assertRaises(ValueError):
            generate_worksheet(3, 5, labels=[])

    def test_labels_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            generate_worksheet(3, 5, labels=[_sample_label(), "牛奶"])


class TestCli(unittest.TestCase):
    def test_read_success(self) -> None:
        code, out, _err = _run_cli(
            ["read", "--energy", "1050", "--protein", "8", "--fat", "12",
             "--carbs", "45", "--sodium", "400"]
        )
        self.assertEqual(code, 0)
        self.assertIn("每 100 g", out)
        self.assertIn("NRV%", out)
        self.assertIn("中等能量", out)

    def test_read_with_serving(self) -> None:
        code, out, _err = _run_cli(
            ["read", "--energy", "1050", "--protein", "8", "--fat", "12",
             "--carbs", "45", "--sodium", "400", "--serving", "25"]
        )
        self.assertEqual(code, 0)
        self.assertIn("每份（25 g）", out)
        self.assertIn("262.5 kJ", out)
        self.assertIn("62.7 kcal", out)

    def test_read_negative_returns_2(self) -> None:
        code, _out, err = _run_cli(
            ["read", "--energy", "-1", "--protein", "8", "--fat", "12",
             "--carbs", "45", "--sodium", "400"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误", err)
        self.assertIn("负数", err)

    def test_read_nan_returns_2(self) -> None:
        code, _out, err = _run_cli(
            ["read", "--energy", "nan", "--protein", "8", "--fat", "12",
             "--carbs", "45", "--sodium", "400"]
        )
        self.assertEqual(code, 2)
        self.assertIn("错误", err)

    def test_read_non_numeric_exits_2(self) -> None:
        code, _out, _err = _run_cli(
            ["read", "--energy", "abc", "--protein", "8", "--fat", "12",
             "--carbs", "45", "--sodium", "400"]
        )
        self.assertEqual(code, 2)

    def test_nrv_success(self) -> None:
        code, out, _err = _run_cli(["nrv", "--nutrient", "fat", "--value", "30"])
        self.assertEqual(code, 0)
        self.assertIn("50.0%", out)

    def test_nrv_unknown_nutrient_returns_2(self) -> None:
        code, _out, err = _run_cli(
            ["nrv", "--nutrient", "sugar", "--value", "30"]
        )
        self.assertEqual(code, 2)
        self.assertIn("未知营养素", err)

    def test_compare_success(self) -> None:
        code, out, _err = _run_cli(
            ["compare", "--a", "面包:1050:8:12:45:400",
             "--b", "牛奶:270:3:3:5:50"]
        )
        self.assertEqual(code, 0)
        self.assertIn("差值（面包 - 牛奶）", out)
        self.assertIn("+780 kJ", out)
        self.assertIn("面包更高", out)

    def test_compare_field_count_returns_2(self) -> None:
        code, _out, err = _run_cli(
            ["compare", "--a", "面包:1050:8:12:45", "--b", "牛奶:270:3:3:5:50"]
        )
        self.assertEqual(code, 2)
        self.assertIn("5 段", err)

    def test_compare_non_numeric_returns_2(self) -> None:
        code, _out, err = _run_cli(
            ["compare", "--a", "面包:1050:8:12:45:x", "--b", "牛奶:270:3:3:5:50"]
        )
        self.assertEqual(code, 2)
        self.assertIn("不是数字", err)

    def test_worksheet_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "worksheet.html")
            code, out, _err = _run_cli(
                ["worksheet", "--count", "8", "--seed", "2026", "--out", path]
            )
            self.assertEqual(code, 0)
            self.assertIn("已写入", out)
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertTrue(content.startswith("<!DOCTYPE html>"))
            self.assertEqual(content.count("<details>"), 8)

    def test_worksheet_write_failure_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "missing", "worksheet.html")
            code, _out, err = _run_cli(["worksheet", "--out", path])
            self.assertEqual(code, 2)
            self.assertIn("写入文件失败", err)

    def test_worksheet_bad_count_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "worksheet.html")
            code, _out, _err = _run_cli(
                ["worksheet", "--count", "0", "--out", path]
            )
            self.assertEqual(code, 2)

    def test_demo_success(self) -> None:
        code, out, _err = _run_cli(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("一、标签解读", out)
        self.assertIn("二、NRV 计算", out)
        self.assertIn("三、食品对比", out)

    def test_help_exit_zero(self) -> None:
        code, out, _err = _run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage: foodlabel", out)
        self.assertIn("read", out)


class TestFormatting(unittest.TestCase):
    def test_format_amount_integer(self) -> None:
        self.assertEqual(format_amount(20.0), "20")

    def test_format_amount_decimal(self) -> None:
        self.assertEqual(format_amount(262.5), "262.5")

    def test_format_amount_half_up(self) -> None:
        self.assertEqual(format_amount(11.25), "11.3")

    def test_format_percent_keeps_one_decimal(self) -> None:
        self.assertEqual(format_percent(20.0), "20.0")
        self.assertEqual(format_percent(12.5), "12.5")

    def test_nutrition_dataclass_fields(self) -> None:
        nutrition = Nutrition(100.0, 1.0, 2.0, 3.0, 4.0)
        self.assertEqual(nutrition.energy_kj, 100.0)
        self.assertTrue(math.isclose(nutrition.energy_kcal, 100.0 / 4.184))


if __name__ == "__main__":
    unittest.main()
