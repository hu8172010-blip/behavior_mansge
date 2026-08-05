from __future__ import annotations

import argparse
import multiprocessing

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="启动人员异常行为与轨迹确认服务",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发时自动重新加载",
    )
    return parser


def main() -> None:
    # Windows 下使用 multiprocessing/spawn 时，防止子进程重复执行入口点
    multiprocessing.freeze_support()
    args = build_parser().parse_args()
    uvicorn.run(
        "anomaly_tracker.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
