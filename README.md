# GreenOpt · 风光储最优配置与调度

[![CI](https://github.com/gonh70216230/greenopt/actions/workflows/ci.yml/badge.svg)](https://github.com/gonh70216230/greenopt/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

面向风、光、储及厂内自发电的**两层容量规划与调度模型**：外层用粒子群算法（PSO）搜索装机容量，
内层用开源 HiGHS MILP 求解器求解小时级最优调度。全部计算、报表与出图由纯 Python 实现，
**不需要 MATLAB、Gurobi 或任何商业求解器**。日常使用只需要修改 `config.py`。

---

## 目录

- [模型结构](#模型结构)
- [快速开始](#快速开始)
- [命令行与环境变量](#命令行与环境变量)
- [数据格式](#数据格式)
- [输出](#输出)
- [求解器与性能](#求解器与性能)
- [建模假设与已知局限](#建模假设与已知局限)
- [项目结构](#项目结构)
- [自检与持续集成](#自检与持续集成)
- [协作](#协作)

---

## 模型结构

**外层（容量）** — 5 维决策变量，由 PSO 搜索：

| 变量 | 含义 | 默认范围 |
| --- | --- | --- |
| `PV` | 光伏装机 | 5 – 40 MW |
| `WT` | 风电装机 | 5 – 40 MW |
| `P_ess` | 储能功率 | 5 – 40 MW |
| `T_ess` | 储能时长 | 2 – 4 h |
| `Gen` | 厂内自发电容量 | 5 – 10 MW |

储能能量按 `E = P × T` 推导。把 `config.py` 的 `fixed` 六项全部填数后，程序会**跳过 PSO**，
只求一次最优调度。

**内层（调度）** — 给定容量后的小时级 MILP：

- 变量：风光与自发电的实际利用 `pv/wt/gen`、购电 `buy`、售电 `sell`、充电 `charge`、
  放电 `discharge`（各 n 个）、SOC（n+1 个），以及可选的互斥二进制。
- 约束：逐时功率平衡；SOC 演化（含自放电与充放效率）；按日/月/年闭合的 SOC 循环；
  购售互斥；充放互斥；SOC 上下限；并网容量限制；可选强制全额消纳。
- 目标：`Σ w·dt·1000·(购电成本 − 售电收益 + 自发电燃料成本)`，典型日按代表天数加权。

**总目标**：年化投资成本（含分档造价与储能循环寿命折算）+ 年化最优运行成本。

---

## 快速开始

要求 Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python run_greenopt.py --quick
```

`--quick` 只用于确认环境和输出链路（典型日 + 小规模 PSO，约 10 秒）。正式计算：

```powershell
python run_greenopt.py
```

完整配置默认采用「典型日粗搜 + 全年精搜」，并包含敏感性分析与全年核准，计算量较大，
请预留充足时间（约 3 分钟至 20 分钟，取决于[求解器设置](#求解器与性能)）。

---

## 命令行与环境变量

| 命令行参数 | 作用 |
| --- | --- |
| `--quick` | 小规模快速试跑，仅验证链路，**不可用于正式结论** |
| `--self-test` | 只跑 7 项一致性自检，不求解完整算例 |
| `--no-progress` | 关闭进度显示（日志重定向时适用） |

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OUTPUT_DIR` | `results` | 结果输出目录 |
| `RANDOM_SEED` | `2026` | PSO 与聚类随机种子 |
| `SOLVER` | `highs` | 仅用于报表回显；`scipy.optimize.milp` 内部固定用 HiGHS |
| `GREENOPT_PROGRESS` | `1` | 设为 `0` 关闭进度显示 |

也可以在项目根目录放一个 `.env`（从 `.env.example` 复制）来覆盖这些设置。

---

## 数据格式

数据放在 `Dataset.xlsx` 的 `BasicData` 工作表，列名必须完全一致：

| 列名 | 含义 | 单位/范围 |
| --- | --- | --- |
| `Buy_Price` | 购电电价 | 元/kWh |
| `Sell_Price` | 售电电价 | 元/kWh |
| `Load` | 负荷 | MW |
| `PV_pu` | 光伏标幺出力 | 0–1 |
| `WT_pu` | 风电标幺出力 | 0–1 |
| `Gen` | 厂内自发电标幺出力（默认） | 0–1 |

每行代表一个小时，行数必须是 24 的整数倍；数值不得为负。
若 `Gen` 已是 MW，请把 `config.py` 中 `data.gen_mode` 改为 `"mw"`。

> `BasicDataTables.xlsx` 是造价与电价的**参考素材**，程序不会读取它；
> 其中的光伏/风电/储能分档造价表已转写到 `config.py`。线路与升压站造价未建模。

---

## 输出

运行后 `results/` 包含：

- **`greenopt_results.xlsx`** —— 中英文各一套工作表（每套 11 张）：
  最优配置、成本与电量、分档明细、典型日调度、典型周调度、PSO 收敛、搜索设置、
  数据说明、专业指标、全年核准、敏感性分析；另有一张全年逐小时 SOC 充放电数值表。
- **`result_summary.json`** —— 机器可读摘要，便于复现与比较不同配置。
- **`fig_*.png`** —— 8 类图表 × 中英双语，600 dpi：

| 图 | 内容 |
| --- | --- |
| `fig_pso_convergence` | 收敛曲线（群体最优 + 种群均值） |
| `fig_source` | 典型日源荷曲线与净负荷 |
| `fig_dispatch` | 出力堆叠图（弃风/弃光/弃自发电按源拆分） |
| `fig_soc` | 储能 SOC 与上下限参考线 |
| `fig_typical_week` | 典型周：堆叠 / 充放电 / SOC 与电价 |
| `fig_cost_breakdown` | 年化成本构成 7 柱 |
| `fig_pro_metrics` | LCOE 双口径 + 三个比例指标 |
| `fig_sensitivity` | 敏感性分析 8 子图 |

图表样式统一由 `greenopt/style.py` 管理：Okabe-Ito 色盲友好配色、中文宋体 / 英文 Times New Roman、
8/9/7 pt 字号、朝内刻度、点状浅灰网格、厘米定尺寸画布。

---

## 求解器与性能

内层是标准 MILP：`scipy.optimize.milp` → **HiGHS**，LP 松弛用对偶修正单纯形，
MILP 走 presolve + 分支割平面。**这一层没有算法短板**，真正的开销来自二进制变量的数量。

项目对两类互斥二进制做了剪枝：

| 剪枝 | 可行依据 | 配置项 |
| --- | --- | --- |
| **购售互斥** | 若某小时售电价 ≤ 购电价，同时购售必被支配：购、售同减 δ 不破坏平衡，目标变化 `δ·(售−购) ≤ 0`。故这些小时的二进制恒可省 | `milp.binary_mode = "arbitrage"` |
| **充放互斥** | 先按 LP 求解，仅当真的出现「同时充放」的小时上补建二进制；无违约时等价于纯 LP | `milp.cd_mode = "auto"`（**默认**） |

**实测**（全年 8760 h，固定容量 PV 30 / WT 20 / ESS 10 MW·20 MWh / Gen 10 MW，`strict=True`）：

| 配置 | 整数变量 | 求解耗时 | 相对加速 | 成本相对差 |
| --- | ---: | ---: | ---: | ---: |
| 原始 `all + all` | 17520 | 16.3 s | 1.0× | — |
| 仅剪购售 `arbitrage + all` | 8849 | 18.1 s | **0.9×** | 1.6e-08 |
| 仅改充放 `all + auto` | 8760 | 10.2 s | 1.6× | 8.7e-07 |
| **两者同时 `arbitrage + auto`** | **89** | **1.27 s** | **12.8×** | 8.7e-07 |

两点结论：

1. **两项必须组合使用**。单独启用购售剪枝反而略慢——剩余的 8849 个二进制让分支树结构变差。
2. 成本差异 ≤ `1e-6`，与求解器相对间隙同量级，可视为同一最优解。

> 默认配置是 `binary_mode="all"` + `cd_mode="auto"`（即上表 1.6× 一行）。
> 想拿到完整的 12.8×，把 `config.py` 里 `binary_mode` 改成 `"arbitrage"` 即可。

**为什么不能直接用 LP 松弛代替 MILP？**

数据中有 **89 个小时售电价高于购电价**。纯 LP 会在这些小时同时买入卖出套利，
使全年总成本低估 **19.15%**（38.72 vs 47.89 百万元/年）。因此 LP 松弛在本问题中
**不能作为最优性下界**，任何基于松弛的间隙论证都必须先处理这 89 个小时。

---

## 建模假设与已知局限

这些不是 bug，是使用前需要知道的边界条件：

1. **并网进出口默认 1e4 MW**，等效于不限，所以**弃电率恒为 0**——售电价恒为正时弃电永远劣于上网。
   要研究弃电，需把 `grid.import_max / export_max` 调到实际并网点容量。
2. **厂内自发电造价 400 元/kW 偏低**（实际燃气/柴油机组约 3000–6000 元/kW），
   导致它必然顶到搜索上界。做敏感性分析时建议乘 3–5 倍复核。
3. **搜索上界会绑定**：默认 `[40, 40, 40, 4, 10]` 下，实测 5 维中有 3 维顶到上界，
   说明真实最优可能在搜索盒之外。
4. **典型日平均会抹平价差结构**：89 个套利小时在 k=3/6/12 的典型日场景中全部消失，
   因此两阶段 PSO 的粗搜阶段实际在优化一个有偏的代理问题。
5. **储能退化只按循环数折算**（`life_mode="cycle_min"`），未建模 DoD、温度、倍率等机制。

---

## 项目结构

```text
config.py                  唯一日常配置入口
run_greenopt.py            运行入口（8 阶段流水线）
requirements.txt           依赖清单
CONTRIBUTING.md            协作约定

greenopt/
  data.py                  数据读取校验、典型日聚类、典型周
  dispatch.py              内层 MILP（含二进制剪枝）
  optimizer.py             外层 PSO 与局部精修
  economics.py             分档造价、年化成本、指标
  sensitivity.py           五维一维敏感性扫描
  progress.py              零依赖进度显示
  style.py                 统一绘图样式（配色/字号/尺寸）
  plots.py                 中英文图表
  reporting.py             中英文 Excel 与 JSON
  selftest.py              7 项一致性自检

.github/workflows/ci.yml   GitHub Actions 自检 + 冒烟
Dataset.xlsx               示例算例数据
BasicDataTables.xlsx       造价与电价参考素材（程序不读取）
```

---

## 自检与持续集成

```powershell
python run_greenopt.py --self-test
```

覆盖 7 项断言：资金回收系数为正、分档线性插值、取顶规则、MILP 可解、
逐时功率平衡残差（实测 `7.1e-15`）、年化投资有限、`E = P × T` 换算。

CI 在 Python 3.11 / 3.12 上跑自检，并额外做一次 `--quick` 端到端冒烟（含出图）。
改动模型或经济口径后请同步更新 `greenopt/selftest.py` 中的断言——
它硬编码了「PV 37.5 MW 的插值单价 = 3041.6667」。

---

## 协作

见 [CONTRIBUTING.md](CONTRIBUTING.md)。约定：`main` 保持可运行、改动走 PR、
提交前跑 `--self-test`、不要提交 `.env` 与 `results/`。

**数据授权提醒**：`Dataset.xlsx` 是 8760 小时的负荷/电价/风光出力数据。
若来自实际场站或第三方数据集，公开前请确认许可；不许可时请替换为合成数据并注明生成方式。

---

## 致谢

本项目为原 MATLAB 版本（`run_greenopt.m` / `cfg_greenopt.m` / `gopt_*` 系列函数）的 Python 移植与扩展，
图表样式与工作表口径均与原版逐项对齐。

## License

[MIT](LICENSE)

---

## English

GreenOpt is a two-level capacity-planning and dispatch model for PV, wind, battery storage,
and on-site generation. A particle-swarm optimiser selects capacities; an open-source HiGHS
MILP solves the hourly economic dispatch. Everything — computation, workbooks, and
publication-quality figures — is pure Python; no MATLAB or commercial solver is required.

Highlights: full-year or weighted representative days, tiered CAPEX, cycle-life-adjusted
storage lifetime, bilingual Excel/figures, a 7-assertion self-test, and CI. Two binary-pruning
strategies reduce the MILP from 17 520 to 89 integer variables — a measured **12.8×** speed-up
with identical cost (relative difference ≤ 1e-6).

Quick start: `pip install -r requirements.txt`, then `python run_greenopt.py --quick`
(smoke test) or `python run_greenopt.py` (full run). Edit `config.py` for all assumptions.
