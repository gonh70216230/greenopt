"""运行入口：python run_greenopt.py [--quick] [--self-test]。"""
from __future__ import annotations

import argparse
from pathlib import Path

from config import get_config
from greenopt.data import build_scenario, load_dataset, typical_week
from greenopt.dispatch import solve_dispatch
from greenopt.economics import annual_capex, metrics, metrics_pro, validate_config
from greenopt.optimizer import SearchResult, optimize
from greenopt.plots import make_plots
from greenopt.progress import set_enabled, step
from greenopt.reporting import export_excel, export_json
from greenopt.selftest import run_selftest
from greenopt.sensitivity import run_sensitivity


def _print_result(result: SearchResult, metric: dict, validation: dict | None):
    print("\n=== GreenOpt | 新能源场站最优配置与调度 ===")
    print("Capacity / 容量: PV={:.3f} MW, Wind={:.3f} MW, ESS={:.3f} MW × {:.3f} h = {:.3f} MWh, Gen={:.3f} MW".format(
        result.cap[0], result.cap[1], result.cap[2], result.cap[3]/result.cap[2] if result.cap[2] else 0, result.cap[3], result.cap[4]))
    print("Annual cost / 年化总成本: {:,.2f} CNY/year | investment / 投资: {:,.2f} | operation / 运行: {:,.2f}".format(
        metric["annual_total"], metric["annual_capex"], metric["annual_operation"]))
    print("Renewable self-use / 风光自用率: {:.2%}; curtailment / 弃电率: {:.2%}; green load share / 绿电负荷占比: {:.2%}".format(
        metric["renewable_self_use_rate"], metric["curtailment_rate"], metric["green_share_of_load"]))
    print("Search / 搜索: {} evaluations, {:.1f} s{}".format(result.n_eval, result.elapsed, " (fixed capacity / 固定容量)" if result.fixed_mode else ""))
    if validation:
        print("Full-year validation / 全年核准: {:,.2f} CNY/year".format(validation["metric"]["annual_total"]))


def main():
    parser = argparse.ArgumentParser(description="GreenOpt: renewable capacity planning and dispatch")
    parser.add_argument("--quick", action="store_true", help="small, fast smoke run / 小规模快速试运行")
    parser.add_argument("--self-test", action="store_true", help="run consistency checks only / 仅运行自检")
    parser.add_argument("--no-progress", action="store_true", help="disable progress bars / 关闭进度显示")
    args = parser.parse_args()
    if args.no_progress:
        set_enabled(False)
    cfg = get_config(); validate_config(cfg)
    out_dir = Path(cfg["path"]["out_dir"]); out_dir.mkdir(parents=True, exist_ok=True)

    total_steps = 8
    with step("读取并校验数据", 1, total_steps):
        df = load_dataset(cfg)
    if args.self_test:
        checks = run_selftest(df, cfg)
        for name, ok, detail in checks: print(f"[{'PASS' if ok else 'FAIL'}] {name} / {detail}")
        raise SystemExit(0 if all(ok for _, ok, _ in checks) else 1)
    if args.quick:
        cfg["time"]["mode"] = "typical_days"; cfg["time"]["n_typical_days"] = 3
        cfg["pso"].update({"two_stage": False, "n_pop": 4, "max_iter": 2, "local_refine": False})
        cfg["sensitivity"]["enable"] = False; cfg["out"]["full_year_check"] = False
        print("Quick mode / 快速模式：仅用于检查环境，不应用于正式结论。")

    with step("构建调度场景", 2, total_steps):
        sc = build_scenario(df, cfg)
    with step("搜索最优容量", 3, total_steps):
        result = optimize(cfg, sc)
    dispatch = result.dispatch
    if cfg["out"]["strict_dispatch"]:
        with step("严格重解（强制充放电互斥）", 4, total_steps):
            strict = solve_dispatch(result.cap, sc, cfg, strict=True)
        if strict["ok"]:
            dispatch = strict; capex, _ = annual_capex(result.cap, cfg, dispatch)
            result = SearchResult(result.s, result.cap, capex+dispatch["cost"], dispatch, capex, result.history,
                                  result.n_eval, result.elapsed, result.fixed_mode)
    with step("计算成本与指标", 5, total_steps):
        metric = metrics(dispatch, result.cap, cfg)
    validation = None
    if cfg["out"]["full_year_check"] and sc.mode != "full_year":
        with step("全年 8760 h 核准", 6, total_steps):
            full = build_scenario(df, cfg, "full_year"); d_full = solve_dispatch(result.cap, full, cfg, strict=True)
        if d_full["ok"]: validation = {"dispatch": d_full, "metric": metrics(d_full, result.cap, cfg)}
        else: print("      -> 全年核准求解失败，跳过")
    with step("典型周调度与敏感性分析", 7, total_steps):
        week_sc = typical_week(df, cfg); week_dispatch = solve_dispatch(result.cap, week_sc, cfg, strict=True)
        sensitivity = run_sensitivity(result, sc, cfg) if cfg["out"]["plot"]["sensitivity"] else None
    pro = metrics_pro(dispatch, result.cap, cfg, sc) if cfg["out"]["plot"]["pro"] else None
    with step("导出结果与图表", 8, total_steps):
        if cfg["out"]["write_excel"]:
            print(f"Excel / 结果工作簿: {export_excel(result, metric, dispatch, sc, sensitivity, out_dir, validation, (week_dispatch, week_sc), cfg)}")
        if cfg["out"]["save_json"]:
            export_json(result, metric, out_dir, pro)
        if cfg["out"]["make_plots"]:
            make_plots(result, metric, dispatch, sc, week_dispatch, week_sc, sensitivity, cfg, out_dir)
            print(f"Figures / 图表: {len(cfg['out']['languages'])} 个语言版本已写入 {out_dir}")
    _print_result(result, metric, validation)


if __name__ == "__main__": main()
