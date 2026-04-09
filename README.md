# Speedia

批量测试订阅节点速度的脚本。

<img width="2186" height="1582" alt="image" src="https://github.com/user-attachments/assets/cd20134e-59ae-4b78-bd8b-19cbf97408c5" />


## 一键安装

推荐直接用一键脚本安装（请保证网络畅通，githubusercontent对网络要求较高）：

```bash
curl -fsSL https://raw.githubusercontent.com/creeveliu/speedia/main/install.sh | bash
```

安装完成后会把程序放到 `~/.local/share/speedia/current/`，并创建 `~/.local/bin/speedia` 软链。随后可以直接使用：

```bash
speedia "<SUB_URL>"
speedia --limit 10 "<SUB_URL>"
speedia update
speedia uninstall
```

`<SUB_URL>` 是必填输入。
可以传订阅地址，也可以直接传原始订阅内容或 base64 文本。
支持原生 Clash/Mihomo YAML 订阅，也支持常见的 Shadowrocket URI 订阅自动转换后测速。

## 支持平台

当前 release 安装包支持：

- macOS Apple Silicon
- macOS Intel
- Linux x86_64

说明：

- Windows 还不支持
- Linux arm64 还不支持
- 我目前只在自己的 macOS 环境实际验证过
- 其他平台虽然已经打包，但我还没有亲自实机验证

## 命令说明

### `speedia "<SUB_URL>"`

执行测速。

```bash
speedia "https://example.com/sub"
speedia --limit 10 "https://example.com/sub"
```

结果会写到系统临时目录下的 `speedia/` 子目录，不会落到当前项目目录。

可选参数：

- `--limit <数字>`：本次最多测速多少个节点，覆盖默认值（默认 `32`）
  - 传 `0` 表示不限，测试全部节点

### `speedia update`

更新到最新 release 版本。

```bash
speedia update
```

### `speedia uninstall`

卸载 `speedia`，并删除安装目录和启动软链。

```bash
speedia uninstall
```

### `speedia --version`

查看当前安装版本。

```bash
speedia --version
```

## 开发调试

```bash
cd /Users/cl/Projects/speedia
uv sync
uv run speedia "<SUB_URL>"
```

运行完成后会生成：

- `speed_results.json`（完整测速结果，保持订阅原始顺序）
- `speed_results.html`（本地网页汇总，生成后会自动打开；订阅链接默认打码，可点小眼睛显示，也可一键截图复制到剪贴板）

结果页会通过本机临时网页服务打开，只监听 `127.0.0.1`。关闭页面后服务会自动退出；如果浏览器异常退出，也会在空闲超时后自动关闭。

## 当前实现

`speedia` 会做这些事：

1. 如果你传的是订阅 URL，就先下载；如果你直接传订阅内容或 base64 文本，就直接解析。随后自动识别原生 Clash/Mihomo YAML 或 Shadowrocket URI 订阅格式。
2. 自动把端口改到独立端口，避免影响现有代理：
   - `port: 17890`
   - `socks-port: 17891`
   - `mixed-port: 17893`
   - `redir-port: 0`
   - `external-controller: 127.0.0.1:19090`
3. 对订阅做测速专用处理：
   - 原生 Clash/Mihomo YAML：提取 `proxies` 生成最小测速配置，不依赖原订阅里的 DNS、规则、`proxy-providers`、`rule-providers`
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
- `LIMIT`：默认最多测速节点数
- `PROXY_URL`：测速请求走的本地代理地址，默认 `socks5://127.0.0.1:17891`
- `TEST_URL`：测速下载地址
- `MAX_TIME`：单节点测速超时（秒）

当前默认值：

- `LIMIT = 32`
- `TEST_URL = https://speed.cloudflare.com/__down?bytes=2000000`
- `MAX_TIME = 16`

## 结果格式

`speed_results.json` 示例结构：

```json
{
  "tested_count": 32,
  "tested_at": "2026-04-08 12:00:00",
  "subscription_url": "https://example.com/sub",
  "results": [
    { "node": "节点A", "mbps": 11.63, "status": "ok" },
    { "node": "节点B", "mbps": null, "status": "fail", "reason": "timeout" }
  ]
}
```
