# 新机安装与自动化边界(2026-11-21 实测模拟)

模拟环境:scratch 全新 HERMES_HOME(scratch 下 `roi-newbox`,HERMES_HOME 指向它),放一条 fixture state.db,跑真实装机/解析代码路径。

## 装一个新机 = 一条命令

**分发用封装版**(`scripts/make-dist.sh` 生成单提交、署名 owner(Jzarkcn.sg)的 `../hermes-roi-dist`,不含开发历史与旧版本 blob):

```bash
hermes plugins install file:///<repo同级>/hermes-roi-dist --enable   # 或 https 市场 URL + --name hermes-roi
# → "Installed (agent half). Restart the gateway for the plugin to take effect."
# 注: file:// 安装的 .git log 会记接收机自己的克隆路径;第三方分发走 https/匿名仓库即无本机信息。
```

实测验证:
- 全包复制进 `<home>/plugins/hermes-roi/`(roi/、dashboard/plugin_api.py+manifest.json、desktop/plugin.js);
- `config.yaml` 自动写入 `plugins.enabled: [hermes-roi]`——**不用去 Capabilities→Plugins 手动开关**(--enable;不加则多一步确认);
- `.install-metadata.json` 记 source + pinned SHA(= dac0338 最新);
- API 半边挂载:gateway 起在装机之后 → 启动时自动加载;已运行的 gateway 需重启一次(CLI 有提示);
- 桌面 pane:app 的 `desktop-plugins/` root 自维护(Electron 从 home 里的统一包自动复制桌面半边;fs watch + 5s poll,新文件夹自动加载,**不用重启 app**);
- 另一条路径:桌面 app → Plugins 页 → catalog "Install here"(两半一起装;本机构 11-06 是手动形态,catalog 路径未在新机端实跑)。

## 数据读取 = 全自动(实测)

新机 home 里只有默认 state.db(4 条会话 fixture),未设任何环境变量:
- collector 经 `get_default_hermes_root()`/`named_profile_home` 自动发现 `["default"]`、会话、tokens、本地占比;
- 摘要/回本当场计算(LV4、BE 日期、曲线 22 点、预测线,全部由 fixture 数字推得);
- 默认样本窗 = 最近 90 天,不用填任何东西;
- 后端**每次请求现读**(sqlite `mode=ro`,无服务端缓存)→ 会话一结束,下次读取就带上。

## 界面刷新 ≠ 全自动(诚实边界)

- `desktop/plugin.js` **没有定时刷新**(无 `refetchInterval`;`setInterval` 只驱动剩余时间倒数,纯前端显示);
- app 全局 QueryClient:`refetchOnWindowFocus: false` + `staleTime: 60s` → **聚焦也不刷**;
- 所以自动化 = **挂载/进 pane 时自动取数 + 输入停顿后自动重算**(防抖),"蹲在 pane 里盯着看"不会自己更新——需要切走再进、或按「重新计算」;
- dev 面板的 5 分钟自动刷新是 roi-dev 的 cron(refresh_dashboard.py → dev 样例板),**不是**插件行为。
- 若要真·全自动:给两个 useQuery 加 `refetchInterval: 30_000~60_000`(改动小,待老板拍板)。

## 装机杂项

- CLI 装机复制整个 repo 树(含 docs/tests/dev/roi-verify-*.png)进 home——公开市场发布前考虑裁剪,或加 `.gitignore` 式排除(未处理)。
- catalog 安装写的 `.hermes-package.json` marker = opt-in 姿态(与 agent 半边 enablement 联动);`--enable` 直接写 enabled。桌面半边 enable 是否严格跟随 agent 行,未在新机实跑验证。
