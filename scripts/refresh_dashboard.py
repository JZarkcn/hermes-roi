#!/usr/bin/env python3
"""Refresh the ROI project dashboard: re-snapshot repo/test facts, regenerate
roi-dashboard.html, update the LAST_REFRESH stamp, and refresh the preview pane.

Output is a short status line (for cron logs).
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path.home() / ".hermes/profiles/roi-dev/cache/scratch"
DASH = SCRATCH / "roi-dashboard.html"
TEMPLATE = REPO / "docs/dashboard-template.html"
STAMP_FILE = SCRATCH / "roi-dashboard.last_refresh"

# Ticket registry for the FIRST-6 plan. State is derived from PROGRESS.md
# below (commits / "done" markers / next-ticket pointer), and P2+ tickets are
# listed dynamically from "Residual / next" and phase notes when they appear.
TICKETS = [
    ("T01", "仓库脚手架 + 参考清单（docs/REFERENCES.md）"),
    ("T02", "只读活动采集器 + 数据契约 + 26 项测试"),
    ("T03", "最小桌面插件注册 + 原生页面 + 只读 /summary"),
    ("T04a", "纯定价 + 四级评判层（Decimal）"),
    ("T04b-data", "费率卡 + Xe FX + 可选电费模型（D-018~D-022）"),
    ("T04b-wire", "GET /economics 端点 + 页面 hero/verdict UI"),
    ("T05", "回本预测 + 四级评判 + 测试（P1 收尾）"),
    ("T06", "Hero UI 对齐截图，fixture → 真实 payload（P2）"),
]

# Evidence rows (k, v, tone) — re-verified from live sources where marked LIVE.
EVIDENCE = [
    ("Hermes 版本", "v0.22.5 stable @ bf0203a794 · Python 3.14.9（git 安装）", "g"),
    ("参考插件", "hermes-activity v0.2.2 @ 0335e954 · MIT", "g"),
    ("state.db", None, "g"),            # LIVE
    ("数据一致性", "159/159 sessions ↔ session_model_usage 精确匹配 · 47 subagent 行", "g"),
    ("只读访问", "mode=ro 连接 · WAL 并发读安全 · 写入被拒绝（含跨 profile 冒烟）", "g"),
    ("模型分类", "基于 base_url / provider 路由，模型名永不单独判定（含云端 Qwen 陷阱 fixture）", "g"),
    ("定价层", "Decimal 全程 · deepseek-flash 费率卡（2026-11-02 官方核验）· Xe 中间价快照 · 可选电费", "g"),
    ("测试", None, "g"),                # LIVE
    ("工作区", None, "g"),              # LIVE (git status)
]

# Risk rows (k, v)
RISKS = [
    ("Reasoning 语义", "Anthropic output_tokens 是否含 extended-thinking 仍为假设，需引用文档后方可单独计费"),
    ("费率卡时效", "deepseek-flash 费率为 2026-11-02 快照，刷新需手动重抓 + 提交（P2 工作流）"),
    ("Home Dashboard", "1.5.0 仅有固定 widget 集，无已验证的第三方注册 API → P3 必须走上游源码 PR"),
    ("远程 profile", "out of MVP；profile picker 须禁用 remote 路由"),
]


def sh(cmd, cwd=REPO, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), shell=isinstance(cmd, str),
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def git_branch_and_shas():
    rc, out, _ = sh("git -C %s status --short --branch" % REPO)
    branch = "?"
    if rc == 0:
        m = re.match(r"^## ([^\s]+)", out.strip())
        if m:
            branch = m.group(1).split("...")[0]
    rc, out, _ = sh("git -C %s log --oneline -12" % REPO)
    commits = []
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]{7,})\s+(.*)", line)
        if m:
            commits.append((m.group(1), m.group(2)))
    rc, out, _ = sh("git -C %s status --short" % REPO)
    lines = out.splitlines()
    untracked = [ln[3:].strip() for ln in lines if ln.startswith("??")]
    modified = [ln for ln in lines if ln.startswith(" M")]
    return branch, commits, untracked, modified


def read_progress():
    p = REPO / "docs" / "PROGRESS.md"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    # Newest entry is LAST in the file (durable journal), so take the last
    # match for "Next ticket:" / "Current phase:".
    next_m = None
    for m in re.finditer(r"Next ticket:\s*\*\*(T[\w.\-]+|P\d+\s*/?\s*T?[\w.\-]*)\*\*", text):
        next_m = m
    next_id = None
    if next_m:
        raw = re.sub(r"\s+", " ", next_m.group(1))
        m2 = re.match(r"^(?:P\d+\s*/?\s*)?(T[\w.\-]+)", raw)
        if m2:
            next_id = m2.group(1)
    phase = "P?"
    for m in re.finditer(r"Current phase:\s*(P\d)", text):
        phase = m.group(1)
    p0_m = re.search(r"\((\d+)\s*of\s*~?(\d+)\s*checklist items", text)
    p0_done, p0_total = (int(p0_m.group(1)), int(p0_m.group(2))) if p0_m else (8, 8)
    # P0 is fully done once P1 has started (phase advanced).
    if int(phase[1]) >= 1:
        p0_done, p0_total = p0_total, p0_total
    return phase, p0_done, p0_total, next_id, text


def run_tests():
    rc, out, err = sh("python3 -m unittest discover -s tests 2>&1", timeout=180)
    tail = (out + "\n" + err)[-2000:]
    ran = re.search(r"Ran (\d+) tests?", tail)
    ok = bool(re.search(r"^OK\s*$", tail, re.M))
    failed_m = re.search(r"FAILED\s*\((\d+)\s+failure[s]?", tail)
    return {
        "ran": int(ran.group(1)) if ran else None,
        "ok": ok,
        "failed": int(failed_m.group(1)) if failed_m else (0 if ok else None),
        "tail": tail.strip().splitlines()[-3:],
    }


def state_db_line():
    # Read-only snapshot of the default profile's state.db (schema v32 at audit
    # time). The live file location may differ from the audit, so keep the
    # audited figures as the verified baseline and only live-check when the
    # file is found.
    live = None
    for cand in (
        os.path.expanduser("~/.hermes/state.db"),
        os.path.expanduser("~/.hermes/sessions/state.db"),
    ):
        if os.path.exists(cand):
            live = cand
            break
    if not live:
        return "150 MB · schema v32 · 205 会话（2026-09-30 → 11-01）· 审计基线，活库路径未找到"
    try:
        con = sqlite3.connect("file:%s?mode=ro" % live, uri=True)
        cur = con.cursor()
        sv = cur.execute("PRAGMA user_version").fetchone()[0]
        n = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        span = cur.execute("SELECT MIN(started_at), MAX(started_at) FROM sessions").fetchone()
        con.close()

        def fmt(x):
            try:
                return datetime.fromtimestamp(x).strftime("%Y-%m-%d")
            except Exception:
                return str(x)
        size = os.path.getsize(live)
        return "%d MB · schema v%s · %d 会话（%s → %s）· %s" % (
            round(size / 1e6, 1), sv, n, fmt(span[0]), fmt(span[1]),
            os.path.basename(os.path.dirname(live)))
    except Exception as e:
        return "150 MB · schema v32 · 205 会话（2026-09-30 → 11-01）· 审计基线（活库读取失败: %s）" % type(e).__name__


def derive_ticket_states(progress_text, next_id, commits):
    """Derive done/active/todo from evidence.

    DONE = the ticket id appears in ANY commit subject (delivered and
    committed) OR a progress entry marks it done/delivered.
    ACTIVE = the ticket id appears in the newest progress entry (the file is
    a journal; the last entry = current state).
    Else TODO.
    """
    # Split into entries at top-level "## Entry" headers; newest = last.
    entries = re.split(r"^## Entry ", progress_text, flags=re.M)
    newest = entries[-1] if entries else progress_text

    done_markers = set()
    for _, subj in commits:
        for m in re.finditer(r"(T\d+[a-z0-9.\-]*)", subj):
            done_markers.add(m.group(1))
    for m in re.finditer(r"Current phase:.*?(T\d+[a-z0-9.\-]*)\s+done", progress_text, re.S):
        done_markers.add(m.group(1))
    for m in re.finditer(r"## Entry.*?—\s*(T\d+[a-z0-9.\-]*)", progress_text, re.S):
        # entry title naming the ticket that entry delivered
        done_markers.add(m.group(1))

    states = {}
    for tid, _ in TICKETS:
        if tid in done_markers or any(tid in d for d in done_markers):
            states[tid] = "done"
        elif re.search(r"\b%s\b" % re.escape(tid), newest):
            # Mentioned in the newest (current) entry but not committed yet
            # -> work in flight.
            states[tid] = "active"
        else:
            states[tid] = "todo"
    return states


CSS = """
  :root {
    --foreground: #e8eaed;
    --muted-foreground: #9aa0a6;
    --accent: #4d9fff;
    --border: #2b3038;
    --card: #1c1f26;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif;
    color: var(--foreground);
    background: #16181d;
    padding: 28px 24px 40px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    min-width: 720px;
  }
  .mono { font-family: "SF Mono", "JetBrains Mono", Menlo, monospace; }
  .top {
    display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
    padding-bottom: 14px; border-bottom: 1px solid var(--border);
  }
  .top h1 { font-size: 19px; font-weight: 650; letter-spacing: .01em; }
  .top .sub { font-size: 11px; text-transform: uppercase; letter-spacing: .14em; color: var(--muted-foreground); }
  .top .refresh {
    margin-left: auto; font-size: 11px; color: var(--muted-foreground);
    display: flex; align-items: center; gap: 8px;
  }
  .top .refresh .pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
  .top .refresh-btn {
    background: var(--accent); color: var(--foreground);
    border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px;
    font-size: 12px; cursor: pointer;
  }
  .top .refresh-btn:hover { filter: brightness(1.15); }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
  .kpi { border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; background: var(--card); }
  .kpi .label { font-size: 10px; text-transform: uppercase; letter-spacing: .13em; color: var(--muted-foreground); margin-bottom: 8px; }
  .kpi .value { font-size: 26px; font-weight: 650; letter-spacing: -.01em; }
  .kpi .value small { font-size: 13px; font-weight: 400; color: var(--muted-foreground); margin-left: 4px; }
  .kpi .hint { font-size: 11px; color: var(--muted-foreground); margin-top: 6px; line-height: 1.4; }
  .kpi.warn .value { color: #e8a33d; }
  .kpi.ok .value { color: var(--accent); }
  .sec { border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px; background: var(--card); }
  .sec h2 {
    font-size: 11px; text-transform: uppercase; letter-spacing: .14em;
    color: var(--muted-foreground); margin-bottom: 14px;
    display: flex; align-items: center; gap: 10px;
  }
  .sec h2::after { content: ""; flex: 1; height: 1px; background: var(--border); }
  .phases { display: flex; gap: 6px; margin-bottom: 12px; }
  .ph { flex: 1; border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
  .ph .name { font-size: 10px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted-foreground); }
  .ph .state { font-size: 13px; font-weight: 600; margin-top: 5px; }
  .ph .bar { height: 3px; border-radius: 2px; background: var(--border); margin-top: 9px; overflow: hidden; }
  .ph .bar i { display: block; height: 100%; background: var(--accent); }
  .ph.current { border-color: var(--accent); }
  .ph.current .state { color: var(--accent); }
  .phase-note { font-size: 12px; color: var(--muted-foreground); line-height: 1.5; }
  .phase-note b { color: var(--foreground); }
  .tgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .t { border: 1px solid var(--border); border-radius: 6px; padding: 12px 13px; }
  .t .tid { font-size: 11px; font-weight: 700; letter-spacing: .05em; }
  .t .tname { font-size: 12.5px; margin-top: 5px; line-height: 1.4; }
  .t .chip {
    display: inline-block; margin-top: 9px; font-size: 10px; letter-spacing: .08em;
    text-transform: uppercase; padding: 2px 8px; border-radius: 4px;
    border: 1px solid var(--border); color: var(--muted-foreground);
  }
  .t.done .tid { color: var(--accent); }
  .t.done .chip { border-color: var(--accent); color: var(--accent); }
  .t.active .chip { background: var(--accent); color: #fff; border-color: var(--accent); }
  .cols { display: grid; grid-template-columns: 1.15fr .85fr; gap: 18px; }
  .row { display: flex; gap: 10px; padding: 7px 0; font-size: 12.5px; align-items: baseline; }
  .row + .row { border-top: 1px solid var(--border); }
  .row .k { color: var(--muted-foreground); min-width: 118px; flex-shrink: 0; }
  .row .v { flex: 1; line-height: 1.45; }
  .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
  .dot.g { background: var(--accent); }
  .dot.y { background: #e8a33d; }
  .commit { display: flex; gap: 12px; align-items: flex-start; padding: 9px 0; }
  .commit + .commit { border-top: 1px solid var(--border); }
  .commit .sha {
    font-size: 11px; padding: 2px 7px; border-radius: 4px;
    border: 1px solid var(--border); color: var(--muted-foreground); flex-shrink: 0;
  }
  .commit .msg { font-size: 12.5px; line-height: 1.4; }
  .untracked { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--border); }
  .untracked .ul { font-size: 11px; text-transform: uppercase; letter-spacing: .1em; color: #e8a33d; margin-bottom: 8px; }
  .untracked code { font-size: 11.5px; background: color-mix(in srgb, var(--accent) 12%, transparent); padding: 2px 6px; border-radius: 4px; display: inline-block; margin: 0 5px 5px 0; }
  .foot { font-size: 11px; color: var(--muted-foreground); line-height: 1.6; padding-top: 4px; }
  .foot b { color: var(--foreground); }
"""

STATE_CHIP = {
    "done": '<span class="chip">✓ 已提交</span>',
    "active": '<span class="chip">● 进行中</span>',
    "todo": '<span class="chip">待启动</span>',
}


def build_html(now, branch, commits, untracked, modified, phase, p0_done, p0_total,
               next_id, test, states, extra_evidence):
    kpi_test_value = ("%d/%d" % (test["ok_count"], test["ran"])) if test["ran"] else "?"
    test_hint = ("全部通过" if test["ok"]
                 else "%d 失败：%s" % (test.get("failed") or 1, test["fail_names"][0] if test["fail_names"] else "见测试输出"))
    commit_count = len(commits)
    last5 = untracked[:5]

    phases = []
    cur_i = int(phase[1]) - 1 if phase[1].isdigit() else 0
    for i, pid in enumerate(["P0", "P1", "P2", "P3", "P4"]):
        labels = {
            "P0": "P0 调研验证", "P1": "P1 经济引擎", "P2": "P2 桌面 MVP",
            "P3": "P3 Home 组件", "P4": "P4 发布",
        }
        cur = pid == phase
        if cur:
            state = "进行中"
            width = int(p0_done * 100 / p0_total) if pid == "P0" else 35
        else:
            state = "已完成" if i < cur_i else "待启动"
            width = 100 if i < cur_i else 0
        phases.append(
            '<div class="ph%s"><div class="name">%s</div><div class="state">%s</div>'
            '<div class="bar"><i style="width:%d%%"></i></div></div>'
            % (" current" if cur else "", labels[pid], state, width))

    tickets = []
    for tid, name in TICKETS:
        st = states.get(tid, "todo")
        cls = st
        tickets.append(
            '<div class="t %s"><div class="tid">%s</div><div class="tname">%s</div>%s</div>'
            % (cls, tid, name, STATE_CHIP[st]))

    ev_rows = []
    for k, v, tone in EVIDENCE:
        live = extra_evidence.get(k, v or "")
        ev_rows.append(
            '<div class="row"><span class="dot %s"></span><span class="k">%s</span>'
            '<span class="v">%s</span></div>' % (tone, k, live))

    risk_rows = [
        '<div class="row"><span class="dot y"></span><span class="k">%s</span>'
        '<span class="v">%s</span></div>' % (k, v) for k, v in RISKS]
    if test["ok"]:
        risk_rows = [r for r in risk_rows if "测试红灯" not in r]
    else:
        risk_rows.insert(0, (
            '<div class="row"><span class="dot y"></span><span class="k">测试红灯</span>'
            '<span class="v">当前 %d 项失败：%s</span></div>'
            % (test.get("failed") or 1,
               "、".join(test["fail_names"][:2]) if test["fail_names"] else "见测试输出")))

    commit_rows = [
        '<div class="commit"><span class="sha mono">%s</span><span class="msg">%s</span></div>'
        % (s, m) for s, m in commits[:5]]

    untracked_html = ""
    if untracked:
        codes = "".join("<code>%s</code>" % u for u in last5)
        untracked_html = (
            '<div class="untracked"><div class="ul">%d 个未跟踪条目 · %d 个已跟踪变更（工作区）</div>%s</div>'
            % (len(untracked), len(modified), codes))

    next_label = next_id or "—"
    next_names = {t[0]: t[1] for t in TICKETS}
    # The journal's "Next ticket" pointer can be stale (a historical entry
    # with no newer pointer). If the pointer names an already-committed
    # ticket, show the true next-up instead.
    if next_label in states and states[next_label] == "done":
        upcoming = [t[0] for t in TICKETS if states.get(t[0]) == "todo"]
        if upcoming:
            next_label = upcoming[0]
    next_hint = next_names.get(next_label, "见 docs/PROGRESS.md 最新条目")
    phase_desc = {
        "P0": "初始化 · 调研 · 验证",
        "P1": "经济引擎（定价/预测/评判）",
        "P2": "桌面 MVP（UI/设置/状态栏）",
        "P3": "Home Dashboard 组件（上游 PR）",
        "P4": "打包 · 性能 · 社区发布",
    }.get(phase, "")

    kpi_test_cls = "ok" if test["ok"] else "warn"

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>ROI — Return on Intelligence · 项目管理面板</title>
<style>%s</style>
</head>
<body>

  <div class="top">
    <h1>ROI — Return on Intelligence</h1>
    <span class="sub">Hermes Desktop 社区插件 · 项目管理面板</span>
    <span class="refresh"><span class="pulse"></span>最新刷新 <span class="mono">%s</span></span>
    <button class="refresh-btn" data-hermes-send="刷新 ROI 项目管理看板：运行 python3 ~/ai/hermes-roi/scripts/refresh_dashboard.py（timeout 240），然后 desktop_preview action=open 打开 ~/.hermes/profiles/roi-dev/cache/scratch/roi-dashboard.html（label=ROI 项目面板），回复一行中文状态">⟳ 刷新看板</button>
  </div>

  <div class="kpis">
    <div class="kpi ok">
      <div class="label">当前阶段</div>
      <div class="value">%s <small>/ P4</small></div>
      <div class="hint">%s</div>
    </div>
    <div class="kpi ok">
      <div class="label">已提交</div>
      <div class="value">%d <small>commits</small></div>
      <div class="hint">分支 %s @ %s</div>
    </div>
    <div class="kpi %s">
      <div class="label">测试套件</div>
      <div class="value">%s</div>
      <div class="hint">%s</div>
    </div>
    <div class="kpi">
      <div class="label">下一票据</div>
      <div class="value mono" style="font-size:19px;padding-top:5px;">%s</div>
      <div class="hint">%s</div>
    </div>
  </div>

  <div class="sec">
    <h2>开发阶段 · Phases</h2>
    <div class="phases">%s</div>
    <div class="phase-note">
      当前 <b>%s — %s</b>。P0 门槛已全部满足（数据契约 + SDK 验证 + 只读采集 + 原生页面）；
      P1 经济引擎进行中，P2 桌面 MVP 紧随其后。
    </div>
  </div>

  <div class="sec">
    <h2>票据状态 · Tickets（首批 6 张）</h2>
    <div class="tgrid">%s</div>
  </div>

  <div class="cols">
    <div class="sec">
      <h2>已验证事实 · Verified</h2>
      %s
    </div>
    <div class="sec">
      <h2>风险 / 不确定 · Risks</h2>
      %s
    </div>
  </div>

  <div class="sec">
    <h2>Git 状态 · %s 分支</h2>
    %s
    %s
  </div>

  <div class="foot">
    快照时间 <b>%s</b> · 分支 <b>%s</b> · 测试命令 <span class="mono">python3 -m unittest discover -s tests</span> → <b>%s</b><br>
    自动刷新：工作日 01–20 点每小时 · 其余时段每 5 分钟 · 仅读取仓库与测试，不修改项目文件。
  </div>

</body>
</html>
""" % (
        CSS,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        phase, phase_desc,
        commit_count, branch, commits[0][0] if commits else "—",
        kpi_test_cls, kpi_test_value, test_hint,
        next_label, next_hint,
        "".join(phases), phase, phase_desc,
        "".join(tickets),
        "".join(ev_rows),
        "".join(risk_rows),
        branch,
        "".join(commit_rows),
        untracked_html,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        branch,
        test_hint,
    )
    return html


def main():
    now = datetime.now()
    branch, commits, untracked, modified = git_branch_and_shas()
    phase, p0_done, p0_total, next_id, progress_text = read_progress()
    test = run_tests()
    test["ok_count"] = (test["ran"] or 0) - (test.get("failed") or 0) if test["ran"] else 0
    # Extract failing test names
    fail_names = re.findall(r"FAIL: (\S+)", test["tail"][-4000:] if len(test["tail"]) > 4000 else "\n".join(test["tail"]))
    test["fail_names"] = fail_names

    states = derive_ticket_states(progress_text, next_id, commits)

    extra = {
        "state.db": state_db_line(),
        "测试": "Ran %s — %s" % (
            test["ran"] or "?",
            "OK" if test["ok"] else "FAILED (%s)" % (test.get("failed") or "?")),
        "工作区": ("%d 个未跟踪 · %d 个已跟踪变更" % (len(untracked), len(modified))
                   if (untracked or modified) else "干净（nothing to commit）"),
    }

    html = build_html(now, branch, commits, untracked, modified, phase, p0_done, p0_total,
                      next_id, test, states, extra)
    DASH.write_text(html, encoding="utf-8")
    STAMP_FILE.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")

    status = "refreshed %s | %s | %s | tests %s | untracked %d" % (
        now.strftime("%H:%M:%S"), branch, phase, test_hint_short(test), len(untracked))
    print(status)


def test_hint_short(test):
    if test["ok"]:
        return "%d/%d OK" % ((test["ran"] - 0), test["ran"])
    return "%d/%d, %d fail" % (test["ok_count"], test["ran"], test.get("failed") or 1)


if __name__ == "__main__":
    main()
