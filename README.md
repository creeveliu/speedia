# Speedia

批量测速 Clash/Mihomo 订阅节点的脚本，命令入口是 `speedia`。

## 快速开始

```bash
cd /Users/cl/Projects/speedia
uv sync
uv run speedia "<SUB_URL>"
```

`<SUB_URL>` 是必填的订阅地址。
支持原生 Clash/Mihomo YAML 订阅，也支持常见的 Shadowrocket URI 订阅自动转换后测速。

## 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/creeveliu/speedia/main/install.sh | bash
```

安装完成后可以直接使用：

```bash
speedia "<SUB_URL>"
speedia update
speedia uninstall
```

运行完成后会生成：

- `speed_results.json`（完整测速结果，保持订阅原始顺序）
- `speed_results.html`（本地网页汇总，方便完整查看结果，生成后会自动打开）

## 当前实现

`speedia` 会做这些事：

1. 下载你传入的订阅配置 URL，并自动识别原生 Clash/Mihomo YAML 或 Shadowrocket URI 订阅格式。
2. 自动把端口改到独立端口，避免影响现有代理：
   - `port: 17890`
   - `socks-port: 17891`
   - `mixed-port: 17893`
   - `redir-port: 0`
   - `external-controller: 127.0.0.1:19090`
3. 对订阅做测速专用处理：
   - 原生 Clash/Mihomo YAML：保留原配置结构，只注入隔离端口和本地 API 密钥
   - Shadowrocket URI：转换为只用于测速的最小 Mihomo 配置
4. 优先使用系统 `mihomo`；没有则自动下载 `v1.19.23` 对应平台二进制到 `~/.cache/speedia/mihomo`，后续直接复用。
5. 启动临时 Mihomo 实例，调用 REST API：
   - 获取 `proxies`
   - 在内部选择可测速的组并切换节点
   - 用 `curl` 测 `speed_download`
6. 在终端按完成顺序逐行输出节点测速结果；失败时会带原因（如 `timeout`、`tls_error`、`http_502`），并写入 `speed_results.json` 和 `speed_results.html`。
7. 结束后自动关闭临时 Mihomo 进程。

## 可配置项（在 `speedia.py` 顶部）

- `DEFAULT_SECRET`：临时 Mihomo API 密钥，脚本会统一写成这个固定值
- `GROUP`：要测试的策略组名称，留空会自动选节点最多的组
- `LIMIT`：本轮最多测速节点数
- `TEST_URL`：测速下载地址
- `MAX_TIME`：单节点测速超时（秒）

## 结果格式

`speed_results.json` 示例结构：

```json
{
  "group": "GLOBAL",
  "tested_count": 50,
  "tested_at": "2026-04-08 12:00:00",
  "subscription_url": "https://example.com/sub",
  "results": [
    { "node": "节点A", "mbps": 11.63, "status": "ok" },
    { "node": "节点B", "mbps": null, "status": "fail", "reason": "timeout" }
  ]
}
```
