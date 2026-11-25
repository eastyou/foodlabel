# foodlabel

[![CI](https://github.com/eastyou/foodlabel/actions/workflows/ci.yml/badge.svg)](https://github.com/eastyou/foodlabel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-brightgreen.svg)](pyproject.toml)

一个用 Python 标准库实现的营养成分表解读工具，帮助师生把包装上的“每 100 g”换算成“每份”，并算出 NRV 占比与能量高低。

## 项目简介

食品包装上的营养成分表通常按每 100 g 标注，但实际吃下去的是“一份”。本项目把每 100 g 的能量、蛋白质、脂肪、碳水化合物、钠换算成每份数值，同时给出以中国营养标签教学常用参考值为基准的 NRV 占比，让“这一包占了一天多少”变得可见。

工具还支持两张标签的横向对比、能量密度分级和可直接打印的 HTML 练习纸，适合初中生物与健康教育课堂上的“读标签”练习。全部计算只依赖标准库，离线可用。

## 特性

- 每 100 g 与每份双向换算，能量同时给出 kJ 与 kcal
- 五种营养素（能量、蛋白质、脂肪、碳水化合物、钠）的 NRV% 一键计算
- 两张标签对比：逐项差值表与 NRV% 高低标注
- 能量密度分级：低能量、中等能量、高能量三档
- 可复现的随机练习纸，答案用 `<details>` 折叠
- 纯标准库、零第三方依赖，Python 3.9 及以上可用

## 安装

```bash
pip install git+https://github.com/eastyou/foodlabel.git
```

在仓库目录内本地安装：

```bash
pip install -e .
```

不安装也可以直接运行：

```bash
python3 -m foodlabel --help
```

## 使用

### read：读懂一张标签

```bash
python3 -m foodlabel read --energy 1050 --protein 8 --fat 12 --carbs 45 --sodium 400 --serving 25
```

输出：

```text
食品：样品
营养素      每 100 g               每份（25 g）           NRV%（每 100 g）
----------  ---------------------  ---------------------  ----------------
能量        1050 kJ（251.0 kcal）  262.5 kJ（62.7 kcal）  12.5%
蛋白质      8 g                    2 g                    13.3%
脂肪        12 g                   3 g                    20.0%
碳水化合物  45 g                   11.3 g                 15.0%
钠          400 mg                 100 mg                 20.0%
能量密度：中等能量（教学参考：每 100 g 低于 400 kJ 为低能量，400 到 1670 kJ 为中等能量，高于 1670 kJ 为高能量）
```

不写 `--serving` 时只输出每 100 g 一栏。

### nrv：算单项 NRV%

```bash
python3 -m foodlabel nrv --nutrient energy --value 1050
```

输出：

```text
营养素：能量
含量：1050 kJ
NRV 参考值：8400 kJ
NRV% = 1050 ÷ 8400 × 100% = 12.5%
```

### compare：两张标签对比

```bash
python3 -m foodlabel compare --a "面包:1050:8:12:45:400" --b "牛奶:270:3:3:5:50"
```

输出：

```text
对比（每 100 g）：面包 vs 牛奶
营养素      面包（每 100 g）  牛奶（每 100 g）  差值（面包 - 牛奶）  NRV% 对比
----------  ----------------  ----------------  -------------------  -------------------------
能量        1050 kJ           270 kJ            +780 kJ              12.5% vs 3.2%（面包更高）
蛋白质      8 g               3 g               +5 g                 13.3% vs 5.0%（面包更高）
脂肪        12 g              3 g               +9 g                 20.0% vs 5.0%（面包更高）
碳水化合物  45 g              5 g               +40 g                15.0% vs 1.7%（面包更高）
钠          400 mg            50 mg             +350 mg              20.0% vs 2.5%（面包更高）
```

标签字符串顺序固定为“名称:能量:蛋白质:脂肪:碳水:钠”。

### worksheet：生成练习纸

```bash
python3 -m foodlabel worksheet --count 8 --seed 2026 --out worksheet.html
```

输出：

```text
已写入 worksheet.html（共 8 题）
```

生成的 HTML 自包含样式，题目混合“读标签算每份”“算 NRV%”“判断能量高低”三类，答案折叠在每道题的 `<details>` 里。

### demo：一次看完全部功能

```bash
python3 -m foodlabel demo
```

依次输出一张标签解读、两条 NRV 计算过程和一组食品对比。

### 参数

| 子命令 | 参数 | 说明 |
| --- | --- | --- |
| `read` | `--energy` | 每 100 g 能量，单位 kJ，必填 |
| `read` | `--protein` | 每 100 g 蛋白质，单位 g，必填 |
| `read` | `--fat` | 每 100 g 脂肪，单位 g，必填 |
| `read` | `--carbs` | 每 100 g 碳水化合物，单位 g，必填 |
| `read` | `--sodium` | 每 100 g 钠，单位 mg，必填 |
| `read` | `--serving` | 每份质量，单位 g，可选 |
| `nrv` | `--nutrient` | `energy`、`protein`、`fat`、`carbs`、`sodium` 之一 |
| `nrv` | `--value` | 每 100 g 含量，能量用 kJ，钠用 mg，其余用 g |
| `compare` | `--a` / `--b` | 两条“名称:能量:蛋白质:脂肪:碳水:钠”字符串 |
| `worksheet` | `--count` | 题目数量，1 到 100，默认 8 |
| `worksheet` | `--seed` | 随机种子，相同种子题目相同，默认 2026 |
| `worksheet` | `--out` | 输出 HTML 路径，必填 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 执行成功 |
| 2 | 参数或数据非法，错误信息输出到标准错误 |

### 关于 NRV 参考值

本工具的 NRV 参考值采用教学简化数据：能量 8400 kJ、蛋白质 60 g、脂肪 60 g、碳水化合物 300 g、钠 2000 mg；能量密度分级阈值同样为课堂讲解用的近似值。这些数字来自营养标签通则的教学材料，仅用于理解标签、做练习题，不构成任何营养建议或医学建议。

## 作为库使用

```python
from foodlabel import read_label, nrv_percent, energy_level

label = read_label(1050, 8, 12, 45, 400, serving=25, name="示例饼干")
print(round(label.per_serving.energy_kj, 1))   # 262.5
print(round(nrv_percent("protein", 8), 1))     # 13.3
print(energy_level(1050))                      # 中等能量
```

传入了负数、非数字或超过上限的值时，会抛出带中文说明的 `ValueError`。

## 开发与测试

仓库只使用标准库，推荐在 Python 3.9 及以上环境开发：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖每份换算、kcal 换算、五种 NRV%、能量分级边界、非法输入、对比表、HTML 练习纸与命令行退出码，共 84 个用例。CI 会在 Ubuntu 上使用 Python 3.9、3.10、3.11、3.12、3.13 运行同一套测试，并执行 `python -m foodlabel --help` 冒烟检查。

## License

[MIT](LICENSE) © 2026 eastyou
