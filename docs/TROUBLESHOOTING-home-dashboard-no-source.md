# 排障记录 — Home Dashboard「unavailable · this source is not responding」

日期：2026-11-01 (UTC+08) · 排查人：roi-dev agent
现象：Home Dashboard 中 `tokens / host / sessions / cron` 四个数据源持续显示
`unavailable · this source is not responding`，而 `gateway / clock / matrix / logs`
正常（截图 23:06）。

---

## 1. 已验证事实（全部经工具执行确认）

### 1.1 数据源与路由
| widget | 数据源 key | 请求 | 后端实现 |
|---|---|---|---|
| tokens | `analytics` | `ctx.rest('/analytics?days=1')` | `hermes_cli/web_routers/analytics.get_usage_analytics` |
| host | `system` | `ctx.rest('/system')` | `hermes_cli/web_routers/status.get_system_stats`（psutil） |
| sessions | `sessions` | `ctx.rest('/sessions?limit=9')` | `hermes_cli/web_routers/sessions.get_sessions` |
| cron | `cron` | `ctx.rest('/cron')` | `hermes_cli/web_routers/cron.list_cron_jobs` |
| gateway | `status` | `host.status()`（**不走 REST**） | 直接取连接状态 → 所以它一直正常 |

- desktop 前端 `~/.hermes/desktop-plugins/hermes-home-dashboard/plugin.js`
  `useHomeData()`（L2700）每 10s 轮询；每个 widget 的文案由 `widgetState(source, data)`
  （L2383）决定：请求失败且无缓存数据 → `unavailable`。
- 后端路由定义在 `~/.hermes/plugins/home-dashboard/dashboard/plugin_api.py`
  （`@router.get("/analytics")` 等，懒加载 core 模块）。

### 1.2 数据本身完全健康（进程外实测，只读 mode=ro）
用 Hermes 自带 python（3.14.9 venv）直接调用后端函数：

```
tokens /analytics(1d)  OK in 0.03s  keys=[by_model, by_task, daily, period_days, skills, tools, totals]
host /system           OK in 0.12s
sessions /sessions(9)  OK in 0.01s
cron /cron(all)        OK in 0.03s  len=9
```

→ **问题不在数据、不在插件、不在 SQL 性能。** 纯粹是 desktop → gateway 的
REST 调用链路失败。

### 1.3 desktop 主进程日志（`~/.hermes/logs/desktop.log`）
失败时记录的是**传输层错误**，不是 401/404/5xx：

```
17:13:21  [hermes:api GET /api/plugins/home-dashboard/analytics?days=1] Error: Gateway ticket bootstrap failed
17:13:21  [hermes:api GET /api/plugins/home-dashboard/cron]        Error: Gateway ticket bootstrap failed
17:13:21  [hermes:api GET /api/plugins/home-dashboard/system]      Error: Gateway ticket bootstrap failed
17:13:21  [hermes:api GET /api/plugins/home-dashboard/sessions?limit=9] Error: Gateway ticket bootstrap failed
21:44:55  [hermes:api GET /api/profiles] Error: Gateway ticket control socket missing
22:50:27  [hermes:api GET /api/local-models/hardware] Error: Gateway ticket bootstrap failed
```

`Gateway ticket bootstrap failed` = 向 gateway 的 unix 控制 socket
（`~/.hermes/gateway.sock`）发 `session-ticket` 申请时 **socket 的 error/close 事件触发**
（electron-main.mjs `mintLocalGatewayTicket`）。socket 存在且归属正确（已验证
`~/.hermes/gateway.sock` 存在、uid=<运行用户>）。

注意：这些错误**同时**影响 `/api/profiles`、`/api/local-models/*`、`/api/logs` ——
即**所有**需要 native ticket 的 REST 调用，不只是 home-dashboard。

### 1.4 时间线
| 时刻 | 事件 |
|---|---|
| 17:13 | hermes-agent 自动同步（update_receipt: sync ok, venv rebuilt）；紧接着 17:13:21 四个 home-dashboard 源全部 `Gateway ticket bootstrap failed` |
| 19:47 / 19:50 | renderer `Uncaught Error: Minified React error #520`（React 19 的 `window is not defined`，发生在 vendor-react 文件顶层 —— 某处代码在模块初始化期就引用了 `window`，**疑似渲染进程崩溃/挂起的前兆**） |
| 21:44:52 | gateway 收到 SIGUSR1（`hermes gateway restart`），优雅重启，21:45:00 控制 socket 重新 listen |
| 22:04:34 | **Hermes.app 启动**（此前 app 已挂/被杀，约 19:47-19:50 崩掉） |
| 22:50:31 | desktop 开始服务 roi-dev profile（`[MULTIPLEX] Now serving profile 'roi-dev'`）；同秒 `dashboard-auth-basic` 在 **launch scope `~/.hermes`** 注册（22:50:31 WARNING 明确说 profile-scope 的注册被忽略） |
| 23:06:43 | 用户截图：四个源 still unavailable；gateway 面板 online（走 host.status()，不经 REST） |

### 1.5 网关侧状态（已验证）
- `~/.hermes/gateway.lock`: pid 24483, `hermes_home: ~/.hermes`（**launch = default**，运行 1h31m，未再重启）。
- `~/.hermes/profiles/roi-dev/gateway.lock`: 同 pid 24483, `hermes_home: .../profiles/roi-dev`
  → **multiplex 进程同时服务 default（launch）+ roi-dev（热加入）**。
- `~/.hermes/logs/gateway.log`: 21:45:00 `Gateway control socket listening at ~/.hermes/gateway.sock`；
  22:50:31 `[MULTIPLEX] Now serving profile 'roi-dev'`。
- 网关 HTTP 端口 57399 上直接 curl：`/api/plugins/home-dashboard/*` 全部返回 **401 Unauthorized**
  （无 ticket 时的预期行为，说明路由活着、插件 API 已挂载）。
- gateway.error.log：无 home-dashboard 相关异常；22:50:31 有
  `Plugin 'basic' tried to register dashboard-auth provider 'basic' from profile scope .../profiles/roi-dev; ignoring it because dashboard auth is owned by launch scope`
  （预期行为，非故障）。
- `dashboard-auth.log`：21:40-23:30 之间**零** session_rejected 记录 → 401 不是 cookie 门拒绝，
  而是 native ticket 根本没发出去（与 desktop.log 的 bootstrap failed 一致）。

### 1.6 native ticket 机制（源码验证，electron-main.mjs + gateway/control_socket.py）
1. desktop 主进程为每次 REST 调用向 `~/.hermes/gateway.sock` 发
   `{"protocol":1,"verb":"session-ticket","params":{profile_id, instance_id, purpose:"native-http"}}`。
2. gateway 校验 peer uid + `instance_id` 匹配后签 30s 单次票；HTTP 请求带
   `X-Hermes-Gateway-Ticket`，网关侧 `authenticate_native_http` 兑换并
   **绑定该票的 profile**（`native_profile_scope` 会把 HERMES_HOME 覆盖到票的 home）。
3. 路由规则（`routedGatewayEndpoint`）：
   - primary（当前 app 启动 profile，无 active-profile.json → **default**）的请求 →
     票的 `profile_id = ~/.hermes`；
   - 非 primary profile（如 roi-dev 的页面）→ 票的 `profile_id = ~/.hermes/profiles/roi-dev`。
4. `TicketStore` 只接受 **served profiles**（`registry.profile_ids()` = 未退役的 authorities）。
5. desktop 侧 `redialLocalGateway`：ticket 相关失败（`Gateway ticket*`）会
   `forgetLocalGatewayDescriptor` + 重新 `hermes --profile X gateway ensure` 并重拨 —— **自愈路径存在**。

### 1.7 为什么「昨天好了，今天又不行」
- 21:44:52 的 `hermes gateway restart`（SIGUSR1）把 gateway 拉回了 **launch=default 且只服务 default** 的状态；
  desktop app 当时是挂的（19:47 崩）。
- 22:04 app 重启时 desktop 只认 default 为 primary；22:50 切到 roi-dev 窗口后 gateway 热服务 roi-dev，
  但 **desktop 主进程与 gateway 之间的 ticket 握手通道处于坏状态**（22:50:27 的 bootstrap failed 是最后一条）。
- 此后 `redialLocalGateway` 的自愈**没有再触发/没有成功**（可能是 21:45-22:04 之间 ensure 缓存了一个
  stale endpoint，redial 重连后握手依旧失败，且错误被吞在 renderer 轮询里）。
- 结论：**这是 desktop↔gateway native-ticket 通道的状态病，不是 home-dashboard 插件、
  不是数据、不是权限配置**。21:44 那次 gateway 重启（或 17:13 那次 update+restart）
  与 19:47 的 app 崩溃叠加后，当前 app 实例的 ticket 握手卡死了。

## 2. 解法（按「昨天的解法」——重启 desktop app）
**彻底退出 Hermes.app（Cmd+Q，不是关窗）后重新打开。**
- app 重启会重新执行 `startHermes` → 丢弃 backend descriptor 缓存 →
  重新 `gateway ensure` + 重新 ticket 握手。
- 若 app 已死：`killall Hermes` 再 `open -a Hermes`（或 `open -a "<hermes-agent>/apps/desktop/release/mac-arm64/Hermes.app"`）。
- **不要**只关窗口；**不必**再动 gateway（它健康）。
- 验证：重开后进 Home，10s 内 tokens/host/sessions/cron 出数；
  `tail ~/.hermes/logs/desktop.log` 不应再有新的 `Gateway ticket bootstrap failed`。

## 3. 若 app 重启后仍复现（升级动作，按序）
1. `hermes gateway restart`（让 multiplexer 干净重建 control socket + ticket store），再重开 app。
2. 检查 `~/.hermes/logs/desktop.log` 中 19:47 的 React #520 是否仍在刷 → 若持续，
   考虑 `hermes update` 拉新 desktop bundle（17:13 同步只动了 agent 侧）。
3. 仍不行：`hermes doctor`。

## 4. 未验证项（诚实声明）
- 19:47:55 的 `React error #520` 与 app 崩溃的因果链**未证实**（无更细的崩溃日志）；
  仅时间上吻合（app 最后日志 19:50，下次启动 22:04）。
- `mintLocalGatewayTicket` 的 error 分支把底层 ECONNREFUSED/EPIPE 等全部压成
  `Gateway ticket bootstrap failed`，**无法从现有日志区分**「socket 拒绝」与「握手超时/响应被拒」。
  需要 gateway 侧对 control socket 的连接日志才能钉死（当前 gateway.log 不记录该层）。
