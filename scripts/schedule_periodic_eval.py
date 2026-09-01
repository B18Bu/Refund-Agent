"""周期评测调度：Windows 计划任务 / 容器 cron / 立即执行（工单 8 任务三）。

用法：
    python scripts/schedule_periodic_eval.py --run-now
    python scripts/schedule_periodic_eval.py --install windows --time 02:00
    python scripts/schedule_periodic_eval.py --install cron --time 02:00
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
PYTHON = sys.executable


def run_now() -> None:
    """立即执行周期评测（固定可执行文件 + 参数数组，不使用 shell=True）。"""
    subprocess.run([PYTHON, "-m", "app.evaluation.runner"], cwd=str(BACKEND_DIR), check=True)


def install_windows(time_str: str, task_name: str) -> None:
    """创建 Windows 计划任务（每日 time_str 触发）。"""
    command_line = f'"{PYTHON}" -m app.evaluation.runner'
    subprocess.run(
        [
            "schtasks", "/Create", "/TN", task_name,
            "/SC", "DAILY", "/ST", time_str,
            "/TR", command_line, "/F",
        ],
        check=True,
    )
    print(f"已创建计划任务 {task_name}（每日 {time_str}），启动目录请设为 {BACKEND_DIR}")


def print_cron(time_str: str) -> None:
    """打印容器内 cron 行，供部署方安装（默认每日 02:00）。"""
    hour = int(time_str.split(":")[0])
    minute = int(time_str.split(":")[1])
    print("# 容器内 cron（建议安装到 worker 容器）")
    print(f"{minute} {hour} * * * cd {BACKEND_DIR} && {PYTHON} -m app.evaluation.runner")


def main() -> None:
    parser = argparse.ArgumentParser(description="周期评测调度")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次评测")
    parser.add_argument("--install", choices=["windows", "cron"], help="安装周期调度")
    parser.add_argument("--time", default="02:00", help="每日触发时间，默认 02:00")
    parser.add_argument("--task-name", default="PeriodicEval", help="Windows 计划任务名")
    args = parser.parse_args()

    if args.run_now:
        run_now()
    elif args.install == "windows":
        install_windows(args.time, args.task_name)
    elif args.install == "cron":
        print_cron(args.time)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
