# AGENTS Notes

当前可用文件：

- `speedia.py`：主脚本
- `speedia`：命令入口（定义在 `pyproject.toml`）
- `pyproject.toml`：项目依赖（`requests`）
- `README.md`：使用说明

## 开发约定（当前版本）

- 脚本依赖 `curl`、`gunzip`（系统命令）和 Python `requests`。
- 不依赖本机常驻 Clash；脚本会自己起临时 Mihomo。
- 端口固定为隔离端口（`17890/17891/17893/19090`）。
- 输出文件固定为 `speed_results.json`（当前工作目录）。

## 建议的下一步改造

1. 把常量改为 CLI 参数（`--group --limit --url --timeout`）。
2. 增加并发测速模式（多进程/线程）并保留串行模式。
3. 支持多轮测速取中位数，降低抖动。
4. 输出 CSV（方便导入表格）。
5. 增加节点过滤（按关键字、国家、倍率）。

## 验证命令

```bash
cd /Users/cl/Projects/Trivial
python3 -m py_compile speedia.py
uv run speedia "<SUB_URL>"
```
