# 协作指南 / Contributing

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Python 3.11 或以上。全流程只依赖 numpy / pandas / scipy / matplotlib / openpyxl，
内层 MILP 由 `scipy.optimize.milp` 内置的 HiGHS 求解，**不需要商业求解器**。

## 提交前必做

```powershell
python run_greenopt.py --self-test   # 7 项一致性断言，必须全 PASS
python run_greenopt.py --quick       # 端到端冒烟，确认能出表出图
```

改了模型或经济口径后，请同步更新 `greenopt/selftest.py` 里的断言——
它目前硬编码了「PV 37.5 MW 的插值单价 = 3041.6667」，调整分档表时该断言需要一起改。

## 分支与提交

- `main` 始终保持可运行，不直接推送。
- 从 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
- 提交信息用祈使句、说明「为什么」而不只是「改了什么」，例如：
  `fix(dispatch): 只在套利小时建购售互斥二进制，全年求解快 7 倍`
- 一个 PR 只做一件事，附带运行结果（成本变化、耗时对比）。

## 不要提交

`.env`、`results/`、`.venv/`、`__pycache__/`、`*.bak` —— 已在 `.gitignore` 中排除。
若误提交了大文件，用 `git rm --cached <file>` 移出索引后再补进 `.gitignore`。

## 数据

`Dataset.xlsx` 是算例输入（8760 h × 6 列）。**提交前请确认其来源与授权**：
若来自实际场站或第三方数据集，需确认是否允许公开；不许可时请替换为合成数据，
并在 README 中说明生成方式。

## 代码风格

- 模块内注释与文档字符串用中文，与现有代码保持一致。
- 新增配置项一律加到 `config.py`，并写进 `reporting._search_rows()` 以便结果可追溯。
- 新增图表走 `style.py` 的配色与字号，不要在 `plots.py` 里写死颜色。
