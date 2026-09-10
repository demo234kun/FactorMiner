# -*- coding: utf-8 -*-
"""
web/app.py —— FactorMiner 可视化 Web 面板（完整版）

启动: uvicorn factorminer.web.app:app --reload --port 8000
功能: 因子库表格 + 因子相关性热力图 + Top 因子 IC 曲线 + 多空收益曲线 + 经验记忆。
图表由服务端生成 SVG/HTML，无任何前端依赖。
"""
from __future__ import annotations
import os
import re
from typing import Optional
import numpy as np
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import HTMLResponse

from FACTOR.step1_data_ingestion.spec import DataConfig, MiningConfig, LLMConfig, SqlConfig, Signal
from FACTOR.step2_factor_mining.ralph_loop import run, summarize
from FACTOR.step2_factor_mining.evaluation import correlation
from FACTOR.step2_factor_mining.expression_engine import ExpressionEngine
from FACTOR.step1_data_ingestion.data_sources import get_data_source, SqlSource
from strategy_backtest.step4_strategy_evolution.agent import run_pipeline
from strategy_backtest.step1_data_adapter.strategy_data import derive_strategy_dataset
from strategy_backtest.step2_template_context.templates import build_templates
from strategy_backtest.step2_template_context.strategy_generator import generate_strategies
from strategy_backtest.step3_backtest_engine.backtest_report import build_backtest_report, backtest_template
from ._store import _store

app = FastAPI(title="FactorMiner 复刻版", version="0.1.0")

_STATE: dict = {"result": None, "data": None, "running": False}
_STRAT_STATE: dict = {"result": None, "running": False}
_GEN_STATE: dict = {"result": None, "running": False}


# --------------------------------------------------------------------------- #
# 设计系统（DESIGN.md）—— ARTi 浅色高级 SaaS
# --------------------------------------------------------------------------- #
_THEME_CSS = """
:root{
  --bg:#f6f5f3; --bg-panel:#ffffff; --bg-panel-2:#ebe7df; --bg-input:#ffffff;
  --border:#e1dcd6; --border-strong:#c9c2b8;
  --text:#171512; --text-dim:#4a4538; --text-faint:#8a8478;
  --accent:#201e19; --gold:#745313; --gold-light:rgba(116,83,19,.12);
  --up:#c2410c; --down:#0e7490; --warn:#a16207;
  --font-ui:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --font-mono:"Cascadia Code",Consolas,monospace;
  --radius-sm:8px; --radius-md:12px; --radius-lg:16px; --radius-full:999px;
  --shadow:0 1px 3px rgba(23,21,18,.06);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ui);
  line-height:1.65;-webkit-font-smoothing:antialiased;min-height:100dvh;
  display:flex;flex-direction:column}
a{color:var(--gold);text-decoration:none;transition:color .2s}
a:hover{color:var(--accent);text-decoration:underline}
/* ---- 顶部命令栏 ---- */
nav.top{position:sticky;top:0;z-index:50;background:rgba(246,245,243,.9);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:20px;padding:0 24px;height:56px}
nav.top .logo{display:flex;align-items:center;gap:9px;font-weight:700;font-size:17px;
  color:var(--text);white-space:nowrap;letter-spacing:-.2px}
nav.top .logo .mark{width:26px;height:26px;border-radius:8px;
  background:linear-gradient(135deg,var(--gold),#b8860b);display:inline-flex;
  align-items:center;justify-content:center;font-size:13px;color:#fff;font-weight:800}
nav.top .menu{display:flex;gap:2px;flex:1;overflow-x:auto}
nav.top .menu a{color:var(--text-dim);font-size:14px;padding:6px 14px;border-radius:var(--radius-full);
  white-space:nowrap;font-weight:500;display:flex;align-items:center;gap:6px}
nav.top .menu a .mi{font-size:12px;color:var(--gold)}
nav.top .menu a:hover{color:var(--text);background:var(--bg-panel-2);text-decoration:none}
nav.top .menu a.active{color:#fff;background:var(--accent)}
nav.top .menu a.active .mi{color:var(--gold-light)}
nav.top .search{display:flex;align-items:center;background:var(--bg-input);border:1px solid var(--border);
  border-radius:var(--radius-full);padding:5px 14px;min-width:200px}
nav.top .search input{background:transparent;border:none;color:var(--text);outline:none;
  font-size:13px;width:100%;font-family:var(--font-ui)}
nav.top .search .kbd{color:var(--text-faint);font-size:11px;font-family:var(--font-mono);white-space:nowrap}
nav.top .cta{background:var(--accent);color:#fff;border:none;padding:8px 18px;
  border-radius:var(--radius-full);font-size:13px;font-weight:600;cursor:pointer;
  font-family:var(--font-ui);transition:transform .15s,box-shadow .2s,background .2s;
  white-space:nowrap}
nav.top .cta:hover{background:#000;transform:translateY(-1px);box-shadow:0 4px 12px rgba(32,30,25,.25)}
nav.top .cta:active{transform:scale(.98)}
/* ---- 壳：全宽主区 ---- */
main{flex:1;min-width:0;padding:28px 32px;overflow-y:auto}
.wrap{max-width:1200px;margin:0 auto}
h1{font-size:32px;font-weight:700;letter-spacing:-.5px;margin:0 0 4px}
h2{font-size:20px;font-weight:700;margin:28px 0 12px;letter-spacing:-.3px}
h3{font-size:16px;font-weight:600;margin:0}
h4{font-size:11px;font-weight:600;margin:12px 0 6px;color:var(--text-dim);text-transform:uppercase;
  letter-spacing:.7px}
p{color:var(--text-dim)}
code{font-family:var(--font-mono);background:var(--bg-panel-2);padding:2px 6px;
  border-radius:6px;font-size:12px;color:var(--gold);word-break:break-all}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.5px;
  font-weight:600}
td{color:var(--text)}
tbody tr{transition:background .15s}
tbody tr:hover{background:var(--bg-panel-2)}
.num{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
button{font-family:var(--font-ui);background:var(--accent);color:#fff;border:none;
  padding:9px 20px;border-radius:var(--radius-full);font-size:14px;font-weight:600;cursor:pointer;
  transition:transform .15s,background .2s,box-shadow .2s}
button:hover{background:#000;transform:translateY(-1px);box-shadow:0 4px 12px rgba(32,30,25,.2)}
button:active{transform:scale(.98)}
button:disabled{opacity:.5;cursor:progress;transform:none;box-shadow:none}
button.ghost{background:var(--bg-panel-2);color:var(--text-dim);border:1px solid var(--border)}
button.ghost:hover{color:var(--text);border-color:var(--border-strong);background:#e3ded4}
textarea{font-family:var(--font-ui);background:var(--bg-input);color:var(--text);border:1px solid var(--border);
  border-radius:var(--radius-md);padding:12px 14px;font-size:14px;line-height:1.7;resize:vertical}
textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--gold-light)}
/* ---- 面板（卡片）---- */
.panel{background:var(--bg-panel);border:1px solid var(--border);border-radius:var(--radius-lg);
  box-shadow:var(--shadow);margin:0 0 20px;overflow:hidden}
.panel .bar{padding:14px 18px 0;font-size:15px;font-weight:700;color:var(--text);
  display:flex;align-items:center;gap:10px;letter-spacing:-.2px}
.panel .bar::after{content:"";flex:1;height:2px;margin-top:8px;
  background:linear-gradient(90deg,var(--gold-light),transparent)}
.panel .bar .dot{width:7px;height:7px;border-radius:50%;background:var(--gold);flex-shrink:0;margin-top:8px}
.panel .body{padding:14px 18px 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px}
.grid .panel{margin:0}
.mcards{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}
.mcard{background:var(--bg-panel-2);border:1px solid var(--border);border-radius:var(--radius-md);
  padding:10px 14px;text-align:center;min-width:96px;flex:1}
.mlabel{font-size:10.5px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.5px}
.mvalue{font-size:18px;font-weight:700;font-family:var(--font-mono);font-variant-numeric:tabular-nums;
  margin-top:2px}
.pill{display:inline-block;padding:2px 10px;border-radius:var(--radius-full);font-size:11px;font-weight:600;
  border:1px solid var(--border);color:var(--text-dim)}
.pill.up{color:var(--up);border-color:rgba(194,65,12,.3);background:rgba(194,65,12,.06)}
.pill.down{color:var(--down);border-color:rgba(14,116,144,.3);background:rgba(14,116,144,.06)}
.pill.warn{color:var(--warn);border-color:rgba(161,98,7,.3);background:rgba(161,98,7,.06)}
.empty{color:var(--text-faint);padding:20px;text-align:center;border:1px dashed var(--border);
  border-radius:var(--radius-md);font-size:13px}
/* ---- 底部状态栏 ---- */
footer.status{height:28px;background:var(--bg-panel);border-top:1px solid var(--border);
  display:flex;align-items:center;gap:16px;padding:0 24px;font-size:11.5px;color:var(--text-faint);
  font-family:var(--font-mono);flex-shrink:0}
footer.status .live{color:var(--up)}
/* ---- LLM 对话界面 ---- */
.chat{display:flex;flex-direction:column;height:calc(100dvh - 56px - 28px);
  max-width:860px;margin:0 auto;padding:16px 0 0}
.chat .msgs{flex:1;overflow-y:auto;padding:8px 4px 16px;display:flex;flex-direction:column;gap:14px}
.msg{display:flex;gap:10px;max-width:82%}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg .avatar{width:30px;height:30px;border-radius:10px;flex-shrink:0;display:flex;
  align-items:center;justify-content:center;font-size:13px;font-weight:700}
.msg.user .avatar{background:var(--accent);color:#fff}
.msg.ai .avatar{background:var(--gold-light);color:var(--gold);border:1px solid rgba(116,83,19,.25)}
.msg .bubble{background:var(--bg-panel);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:10px 14px;font-size:14px;line-height:1.7;box-shadow:var(--shadow)}
.msg.user .bubble{background:var(--accent);color:#fff;border-color:var(--accent)}
.msg .bubble .t{white-space:pre-wrap;word-break:break-word}
.msg .bubble table{font-size:12px;margin:8px 0 2px}
.msg .bubble .saved{font-size:12px;color:var(--down);margin-top:6px}
.msg .bubble code{background:rgba(116,83,19,.1);color:var(--gold)}
.chat .inputbar{border-top:1px solid var(--border);padding:12px 0 16px;
  display:flex;gap:10px;align-items:flex-end}
.chat .inputbar textarea{flex:1;border-radius:var(--radius-lg);min-height:48px;max-height:160px}
.chat .inputbar button{height:48px;padding:0 22px;border-radius:var(--radius-full)}
.chat .suggest{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.chat .suggest button{background:var(--bg-panel);border:1px solid var(--border);color:var(--text-dim);
  font-size:12.5px;padding:6px 14px;border-radius:var(--radius-full)}
.chat .suggest button:hover{color:var(--accent);border-color:var(--gold);background:var(--gold-light)}
.typing{display:inline-flex;gap:4px;align-items:center;padding:4px 2px}
.typing span{width:6px;height:6px;border-radius:50%;background:var(--gold);
  animation:blink 1.2s infinite}
.typing span:nth-child(2){animation-delay:.2s}.typing span:nth-child(3){animation-delay:.4s}
@keyframes blink{{0%,80%,100%{{opacity:.25}}40%{{opacity:1}}}}
@media(max-width:900px){{
  .chat{{padding:8px 0 0}}
  .msg{{max-width:92%}}
}}
"""


def _PAGE_FRAME(title: str, active: str, body: str, panel_bar: str = "") -> str:
    """顶部命令栏 + 全宽主区 + 底部状态栏（单栏布局）。"""
    menu = [
        ("/", "主页", "⌘"),
        ("/library/factors", "因子库", "◫"),
        ("/library/factor-exp", "因子经验", "✎"),
        ("/library/strategies", "策略库", "▦"),
        ("/library/strategy-exp", "策略经验", "◈"),
    ]
    menu_html = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">'
        f'<span class="mi">{ico}</span>{label}</a>'
        for href, label, ico in menu
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{_THEME_CSS}</style></head>
<body>
<nav class="top">
  <div class="logo"><span class="mark">F</span>Factor<span style="color:var(--gold)">Miner</span></div>
  <div class="menu">{menu_html}</div>
  <button class="cta" onclick="location.href='/'">立即体验</button>
</nav>
<main><div class="wrap">{body}</div></main>
<footer class="status">
  <span><span class="live">●</span> 数据源: 本地 Postgres · bars_30m</span>
  <span>FactorMiner v0.1</span>
  <span style="margin-left:auto" id="fm-clock"></span>
</footer>
<script>
function _fmClock(){{var d=new Date(),p=function(n){{return n<10?'0'+n:n}};
document.getElementById('fm-clock').textContent=d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds());}}
_fmClock();setInterval(_fmClock,1000);
</script>
</body></html>"""


def _default_cfgs():
    data_cfg = DataConfig(source="synthetic", market="csi500", freq="10min",
                          start="2024-01-01", end="2026-12-31",
                          n_instruments=15, n_periods=500, seed=0)
    mining_cfg = MiningConfig(tau_ic=0.03, theta=0.5, k_lib=12, batch_size=20,
                              replace_min_ic=0.08, replace_ic_ratio=1.3,
                              seed=0, max_iterations=15)
    llm_cfg = LLMConfig(backend="deepseek", model="deepseek-chat",
                        api_key_env="DEEPSEEK_API_KEY", base_url="https://api.deepseek.com",
                        temperature=0.8, max_tokens=2048, fallback="template", seed=0)
    return data_cfg, mining_cfg, llm_cfg


# --------------------------------------------------------------------------- #
# 真实数据（线上 SQL）分支：env 注入 URI 即启用，否则走合成兜底
# --------------------------------------------------------------------------- #
def _load_real_md(start: str, end: str, table: Optional[str] = None):
    """若设置了 FACTORMINER_SQL_URI / QLIB_SQL_URI，则直连 Postgres 取真实行情；
    否则返回 None，上层回退到合成数据。docker 内的 db:5432 自动改写为 localhost:5432。"""
    uri = os.environ.get("FACTORMINER_SQL_URI") or os.environ.get("QLIB_SQL_URI")
    if not uri:
        return None
    uri = uri.replace("db:5432", "localhost:5432")
    table = table or os.environ.get("FACTORMINER_SQL_TABLE", "bars_d")
    raw = os.environ.get("FACTORMINER_INSTRUMENTS", "")
    insts = [re.sub(r"\.(SH|SZ|BJ|XSHG|XSHE)$", "", x.strip())
             for x in raw.split(",") if x.strip()] or None
    cfg = SqlConfig(uri=uri, table=table, instruments=insts)
    return SqlSource().load(cfg, start, end, instruments=insts)


# --------------------------------------------------------------------------- #
# 可视化辅助
# --------------------------------------------------------------------------- #
def _corr_matrix(result):
    lib = result.library
    n = len(lib)
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                mat[i][j] = 1.0
            else:
                a = Signal(lib[i].formula, lib[i].signal)
                b = Signal(lib[j].formula, lib[j].signal)
                mat[i][j] = abs(correlation(a, b))
    return mat, [f.id for f in lib]


def _ls_curve(signal: np.ndarray, target: np.ndarray):
    T, M = signal.shape
    k = max(1, M // 5)
    rets = np.zeros(T)
    for t in range(T):
        s = signal[t]
        tg = target[t]
        order = np.argsort(s)
        long = tg[order[-k:]]
        short = tg[order[:k]]
        rets[t] = float(long.mean() - short.mean())
    rets = np.nan_to_num(rets, 0.0)
    cum = np.cumprod(1.0 + rets)
    return rets, cum


def _ic_series(signal: np.ndarray, target: np.ndarray):
    from FACTOR.step1_data_ingestion.spec import spearman_per_t
    per_t = spearman_per_t(signal, target)
    return np.nan_to_num(per_t, 0.0)


def _svg_line(values, w=620, h=170, color="#201e19", title=""):
    if len(values) == 0:
        return "<svg></svg>"
    v = np.asarray(values, float)
    v = np.nan_to_num(v, nan=0.0)
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-9:
        hi = lo + 1.0
    pad_l, pad_r, pad_t, pad_b = 34, 16, 22, 26
    xs = np.linspace(pad_l, w - pad_r, len(v))
    ys = h - pad_b - (v - lo) / (hi - lo) * (h - pad_t - pad_b)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    grid = ""
    for i in range(5):
        gy = h - pad_b - i / 4 * (h - pad_t - pad_b)
        val = lo + i / 4 * (hi - lo)
        grid += (f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" '
                 f'stroke="#e1dcd6" stroke-width="1" stroke-dasharray="3 4"/>')
        grid += (f'<text x="4" y="{gy+3:.1f}" font-size="10" fill="#8a8478" '
                 f'font-family="Consolas,monospace">{val:.3g}</text>')
    area = f"{pts} {w-pad_r:.1f},{h-pad_b:.1f} {pad_l:.1f},{h-pad_b:.1f}"
    return f"""
    <svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="width:100%;height:auto;display:block">
      <defs>
        <linearGradient id="g{abs(hash(title))%10000}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{color}" stop-opacity="0.15"/>
          <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="{w}" height="{h}" fill="#fbfaf8" rx="12"/>
      {grid}
      <polygon points="{area}" fill="url(#g{abs(hash(title))%10000})"/>
      <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"
        stroke-linejoin="round" stroke-linecap="round"/>
      <text x="{pad_l}" y="14" font-size="11" fill="#4a4538"
        font-family="Consolas,monospace">{title}</text>
    </svg>"""


def _heatmap_html(mat, labels):
    n = len(labels)
    cells = ""
    for i in range(n):
        row = ""
        for j in range(n):
            v = mat[i][j]
            # 浅色热力：白底上金色强度
            g = int(200 * v)
            bg = f"rgb(246,{242 - g//2},{220 - g//3})" if v > 0.05 else "#ffffff"
            row += f"<td style='background:{bg};text-align:center;font-size:10px;color:{'#745313' if v>0.5 else '#8a8478'}'>{v:.2f}</td>"
        cells += f"<tr><td style='font-size:10px;color:var(--text-dim)'>{labels[i]}</td>{row}</tr>"
    head = "<th></th>" + "".join(f"<th style='font-size:10px'>{l}</th>" for l in labels)
    return f"<table style='border-collapse:collapse'><thead><tr>{head}</tr></thead><tbody>{cells}</tbody></table>"


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def index():
    body = """
    <div class="chat">
      <div class="suggest">
        <button onclick="sendQuick('我想做一个低波动轮动策略，熊市防御')">低波动轮动</button>
        <button onclick="sendQuick('生成一个动量因子')">动量因子</button>
        <button onclick="sendQuick('做多近期涨幅最大的股票，做空跌幅最大的')">截面动量策略</button>
        <button onclick="sendQuick('看看策略库里有什么')">查看策略库</button>
      </div>
      <div class="msgs" id="msgs">
        <div class="msg ai">
          <div class="avatar">F</div>
          <div class="bubble"><div class="t">你好，我是 FactorMiner 策略助手。告诉我你的想法，我可以：
<b>· 生成策略</b> — 输入策略思路，自动翻译成信号公式并回测
<b>· 生成因子</b> — 输入因子想法，生成单因子并验证 IC
<b>· 查询记忆库</b> — 查看因子库 / 策略库 / 历史经验
试试输入：&quot;我想做一个低波动轮动策略，熊市防御&quot;</div></div>
        </div>
      </div>
      <div class="inputbar">
        <textarea id="inp" rows="1" placeholder="输入你的策略想法…  (Enter 发送, Shift+Enter 换行)"></textarea>
        <button onclick="sendMsg()">发送</button>
      </div>
    </div>
    <script>
    var _busy = false;
    function el(id){return document.getElementById(id)}
    function addMsg(role, html){
      var m = document.createElement('div');
      m.className = 'msg ' + role;
      var a = document.createElement('div'); a.className = 'avatar';
      a.textContent = role === 'user' ? '我' : 'F';
      var b = document.createElement('div'); b.className = 'bubble';
      b.innerHTML = html;
      m.appendChild(a); m.appendChild(b);
      el('msgs').appendChild(m);
      el('msgs').scrollTop = el('msgs').scrollHeight;
      return m;
    }
    function esc(s){
      var d = document.createElement('div'); d.textContent = s; return d.innerHTML;
    }
    function typing(){
      var m = addMsg('ai', '<div class="typing"><span></span><span></span><span></span></div>');
      return m;
    }
    function sendQuick(t){
      el('inp').value = t; sendMsg();
    }
    function sendMsg(){
      var t = el('inp').value.trim();
      if (!t || _busy) return;
      _busy = true;
      el('inp').value = '';
      addMsg('user', esc(t));
      var ty = typing();
      fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: t})
      }).then(function(r){return r.json()}).then(function(d){
        ty.remove();
        if (d.error){ addMsg('ai', '<div class="t">出错了: ' + esc(d.error) + '</div>'); }
        else { addMsg('ai', d.html || esc(d.reply || '')); }
      }).catch(function(e){
        ty.remove();
        addMsg('ai', '<div class="t">请求失败: ' + esc(String(e)) + '</div>');
      }).finally(function(){_busy = false});
    }
    el('inp').addEventListener('keydown', function(e){
      if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); sendMsg(); }
    });
    </script>"""
    return _PAGE_FRAME("主页 · FactorMiner", "/", body)


# --------------------------------------------------------------------------- #
# 四个记忆库页面
# --------------------------------------------------------------------------- #
def _factor_lib_preview(limit: int = 6) -> str:
    try:
        fs = _store.list_factors(limit=limit)
    except Exception:
        return "<p>数据库不可用</p>"
    if not fs:
        return "<p>因子库为空。去主页对话生成因子。</p>"
    rows = "".join(
        f"<tr><td class='num'>{f['id']}</td><td><code>{f['formula'][:50]}</code></td>"
        f"<td class='num' style='color:{'var(--up)' if f['ic']>=0 else 'var(--down)'}'>{f['ic']:.4f}</td></tr>"
        for f in fs)
    return f"<table style='font-size:12px'><thead><tr><th>ID</th><th>公式</th><th>IC</th></tr></thead><tbody>{rows}</tbody></table>"


def _strategy_lib_preview(limit: int = 6) -> str:
    try:
        ss = _store.list_strategies(limit=limit)
    except Exception:
        return "<p>数据库不可用</p>"
    if not ss:
        return "<p>策略库为空。去主页对话生成策略。</p>"
    rows = "".join(
        f"<tr><td class='num'>{s['id']}</td><td>{s['name']}</td>"
        f"<td class='num' style='color:{'var(--up)' if s['sharpe']>=0 else 'var(--down)'}'>{s['sharpe']:.2f}</td>"
        f"<td class='num' style='color:{'var(--up)' if s['total_return']>=0 else 'var(--down)'}'>{s['total_return']*100:.1f}%</td></tr>"
        for s in ss)
    return f"<table style='font-size:12px'><thead><tr><th>ID</th><th>名称</th><th>Sharpe</th><th>总收益</th></tr></thead><tbody>{rows}</tbody></table>"


@app.get("/library/factors", response_class=HTMLResponse)
def library_factors():
    fs = _store.list_factors(limit=500)
    rows = ""
    for i, f in enumerate(fs):
        icv = float(f.get("ic", 0) or 0)
        pv = float(f.get("ave_p", 1.0) or 1.0)
        mc = float(f.get("max_corr", 0) or 0)
        redundant = mc >= 0.8
        p_color = "var(--up)" if pv < 0.05 else ("var(--warn)" if pv < 0.2 else "var(--text-dim)")
        expl = f.get("explanation", "") or ""
        expl_html = (f"<div class='expl' id='expl{i}' style='display:none;color:var(--text-dim);"
                     f"font-size:12px;margin-top:6px'>{expl}</div>"
                     f"<button class='ghost' style='font-size:11px;padding:2px 10px' "
                     f"onclick=\"var e=document.getElementById('expl{i}');e.style.display=e.style.display==='none'?'block':'none'\">解释</button>"
                     if expl else "")
        rows += (f"<tr><td class='num'>{f['id']}</td><td>{f['name']}</td><td><code>{f['formula']}</code></td>"
                 f"<td class='num' style='color:{'var(--up)' if icv>=0 else 'var(--down)'}'>{icv:.4f}</td>"
                 f"<td class='num'>{float(f.get('icir',0) or 0):.3f}</td>"
                 f"<td class='num' style='color:{p_color}'>{pv:.4f}</td>"
                 f"<td class='num' style='color:{'var(--warn)' if redundant else 'var(--text-dim)'}'>{mc:.2f}{' ⚠' if redundant else ''}</td>"
                 f"<td>{f['source']}</td><td>{expl_html}</td></tr>")
    rows = rows or "<tr><td colspan=9>（空）</td></tr>"
    body = f"""
    <h1>因子库</h1>
    <p>全部因子与效果（{len(fs)} 条）· ave|p| 越小越显著（&lt;0.05 显著）· maxCorr≥0.8 标记冗余 ⚠</p>
    {_panel("因子库", f"""
      <table><thead><tr><th>ID</th><th>名称</th><th>公式</th><th>IC</th><th>ICIR</th><th>ave|p|</th><th>maxCorr</th><th>来源</th><th>解释</th></tr></thead>
      <tbody>{rows}</tbody></table>""")}"""
    return _PAGE_FRAME("因子库 · FactorMiner", "/library/factors", body)


@app.get("/library/factor-exp", response_class=HTMLResponse)
def library_factor_exp():
    exps = _store.list_factor_experience(limit=300)
    rows = "".join(
        f"<tr><td class='num'>{e['id']}</td><td><span class='pill {'warn' if e['kind']=='forbidden' else ('up' if e['kind']=='pattern' else '')}'>{e['kind']}</span></td>"
        f"<td><code>{e['content']}</code></td><td style='color:var(--text-dim);font-size:12px'>{e['detail']}</td></tr>"
        for e in exps) or "<tr><td colspan=4>（空）</td></tr>"
    body = f"""
    <h1>因子经验库</h1>
    <p>因子挖掘的成功模式 / 禁区 / 洞察（{len(exps)} 条）</p>
    {_panel("因子经验", f"""
      <table><thead><tr><th>ID</th><th>类型</th><th>内容</th><th>详情</th></tr></thead>
      <tbody>{rows}</tbody></table>""")}"""
    return _PAGE_FRAME("因子经验 · FactorMiner", "/library/factor-exp", body)


@app.get("/library/strategies", response_class=HTMLResponse)
def library_strategies():
    ss = _store.list_strategies(limit=500)
    rows = "".join(
        f"<tr><td class='num'>{s['id']}</td><td>{s['name']}</td><td>{s['category']}</td><td><code>{s['signal'][:60]}</code></td>"
        f"<td class='num' style='color:{'var(--up)' if s['sharpe']>=0 else 'var(--down)'}'>{s['sharpe']:.2f}</td>"
        f"<td class='num' style='color:{'var(--up)' if s['total_return']>=0 else 'var(--down)'}'>{s['total_return']*100:.1f}%</td>"
        f"<td class='num'>{s['max_drawdown']*100:.1f}%</td><td class='num'>{s['win_rate']*100:.1f}%</td></tr>"
        for s in ss) or "<tr><td colspan=8>（空）</td></tr>"
    body = f"""
    <h1>策略库</h1>
    <p>各类策略与回测效果（{len(ss)} 条，按 Sharpe 排序）</p>
    {_panel("策略库", f"""
      <table><thead><tr><th>ID</th><th>名称</th><th>类型</th><th>信号</th><th>Sharpe</th><th>总收益</th><th>回撤</th><th>胜率</th></tr></thead>
      <tbody>{rows}</tbody></table>""")}"""
    return _PAGE_FRAME("策略库 · FactorMiner", "/library/strategies", body)


@app.get("/library/strategy-exp", response_class=HTMLResponse)
def library_strategy_exp():
    exps = _store.list_strategy_experience(limit=300)
    rows = "".join(
        f"<tr><td class='num'>{e['id']}</td><td>{e['strategy_name']}</td>"
        f"<td><span class='pill {'up' if e['outcome']=='success' else 'down'}'>{e['outcome']}</span></td>"
        f"<td>{e['regime']}</td><td class='num' style='color:{'var(--up)' if e['sharpe']>=0 else 'var(--down)'}'>{e['sharpe']:.2f}</td>"
        f"<td style='color:var(--text-dim);font-size:12px'>{e['reason']}</td></tr>"
        for e in exps) or "<tr><td colspan=6>（空）</td></tr>"
    body = f"""
    <h1>策略经验库</h1>
    <p>哪些策略在什么情境下失效 / 有效（{len(exps)} 条）</p>
    {_panel("策略经验", f"""
      <table><thead><tr><th>ID</th><th>策略</th><th>结果</th><th>情境</th><th>Sharpe</th><th>原因</th></tr></thead>
      <tbody>{rows}</tbody></table>""")}"""
    return _PAGE_FRAME("策略经验 · FactorMiner", "/library/strategy-exp", body)


@app.post("/mine")
def mine():
    if _STATE["running"]:
        raise HTTPException(409, "已在运行中")
    _STATE["running"] = True
    try:
        data_cfg, mining_cfg, llm_cfg = _default_cfgs()
        real_md = _load_real_md(data_cfg.start, data_cfg.end)
        if real_md is not None:
            result = run(data_cfg, mining_cfg, llm_cfg,
                         memory_path="memory_state_real.json", md=real_md)
            _STATE["data"] = real_md
            src = "sql"
        else:
            result = run(data_cfg, mining_cfg, llm_cfg, memory_path="memory_state.json")
            _STATE["data"] = get_data_source(data_cfg).load(data_cfg)
            src = "synthetic"
        _STATE["result"] = result
        return {"ok": True, "source": src,
                "summary": summarize(result),
                "library": [{"id": f.id, "formula": f.formula} for f in result.library]}
    finally:
        _STATE["running"] = False


@app.get("/api/library")
def api_library():
    res = _STATE["result"]
    if not res:
        return []
    return [{"id": f.id, "formula": f.formula, "ic": round(float(f.ic), 4),
            "icir": round(float(f.icir), 3), "max_corr": round(float(f.max_corr), 2)}
           for f in res.library]


@app.get("/api/memory")
def api_memory():
    res = _STATE["result"]
    if not res:
        return {"patterns": [], "forbidden": [], "insights": []}
    return {"patterns": res.memory.patterns, "forbidden": res.memory.forbidden,
            "insights": res.memory.insights}


# --------------------------------------------------------------------------- #
# 策略自动进化智能体 页面
# --------------------------------------------------------------------------- #
def _strategy_html() -> str:
    s = _STRAT_STATE.get("result")
    if not s:
        body = ("<h1>策略自动进化智能体</h1>"
                "<p>先在 2024 数据上训练经验记忆，再在 2025 上滚动监控/减仓/失灵自动进化。</p>"
                "<button onclick=\"fetch('/strategy/run',{method:'POST',body:JSON.stringify({use_llm:false}),headers:{'Content-Type':'application/json'}}).then(()=>location.reload())\">运行（模板兜底，快速）</button> "
                "<button onclick=\"fetch('/strategy/run',{method:'POST',body:JSON.stringify({use_llm:true}),headers:{'Content-Type':'application/json'}}).then(()=>location.reload())\">运行（DeepSeek 进化）</button>")
        return _PAGE_FRAME("策略进化 · FactorMiner", "/strategy", body)

    log = s["log"]
    mem = s["memory"]
    n_warn = sum(1 for x in log if x.action == "risk_warn")
    n_evol = sum(1 for x in log if x.action == "evolve")
    st = mem.stats()

    rows = "".join(
        f"<tr><td class='num'>{x.t0}-{x.t1}</td><td>{x.regime}</td>"
        f"<td><span class='pill {'warn' if x.action=='risk_warn' else ('up' if x.action=='evolve' else '')}'>{x.action}</span></td>"
        f"<td class='num' style='color:{'var(--up)' if x.live_sharpe>=0 else 'var(--down)'}'>{x.live_sharpe:+.2f}</td>"
        f"<td style='color:var(--text-dim);font-size:12px'>{x.note}</td></tr>"
        for x in log
    )

    succ = mem.successes[:6]
    fail = mem.failures[:6]
    succ_html = "<br>".join(
        f"• [{e.strategy_name}] regime={e.regime} Sharpe=<span class='num'>{e.metrics.get('sharpe',0):.2f}</span> — {e.reason}"
        for e in succ) or "（无）"
    fail_html = "<br>".join(
        f"• [{e.strategy_name}] regime={e.regime} Sharpe=<span class='num'>{e.metrics.get('sharpe',0):.2f}</span> — {e.reason}"
        for e in fail) or "（无）"

    body = f"""
    <h1>策略自动进化智能体</h1>
    <p>资产数 <b class='num'>{s['n_assets']}</b> · 策略模板 <b class='num'>{s['n_templates']}</b> ·
       2025 窗口 <b class='num'>{len(log)}</b> ·
       <span class='pill warn'>风险提示(减仓) {n_warn}</span>
       <span class='pill up'>失灵进化 {n_evol}</span></p>
    <button onclick="fetch('/strategy/run',{{method:'POST',body:JSON.stringify({{use_llm:false}}),headers:{{'Content-Type':'application/json'}}}}).then(()=>location.reload())">重跑（模板兜底）</button>
    <button class="ghost" onclick="fetch('/strategy/run',{{method:'POST',body:JSON.stringify({{use_llm:true}}),headers:{{'Content-Type':'application/json'}}}}).then(()=>location.reload())">重跑（DeepSeek）</button>

    <h2>2025 进化轨迹</h2>
    {_panel("2025 进化轨迹", f"""
      <table><thead><tr><th>窗口</th><th>regime</th><th>动作</th><th>liveSharpe</th><th>说明</th></tr></thead>
      <tbody>{rows}</tbody></table>""")}

    <h2>策略经验记忆（<span class='num'>{st['success']}</span> 成功 / <span class='num'>{st['fail']}</span> 失败）</h2>
    <div class="grid">
      {_panel("成功体验样例", f"<p>{succ_html}</p>")}
      {_panel("失败体验样例", f"<p>{fail_html}</p>")}
    </div>"""
    return _PAGE_FRAME("策略进化 · FactorMiner", "/strategy", body)


@app.get("/strategy", response_class=HTMLResponse)
def strategy_page():
    return _strategy_html()


@app.post("/strategy/run")
def strategy_run(use_llm: bool = False):
    if _STRAT_STATE["running"]:
        raise HTTPException(409, "已在运行中")
    _STRAT_STATE["running"] = True
    try:
        data_cfg, _, _ = _default_cfgs()
        real_md = _load_real_md(data_cfg.start, data_cfg.end)
        if real_md is not None:
            ds = derive_strategy_dataset(real_md)
            res = run_pipeline(use_llm=use_llm, ds=ds,
                              memory_path="strategy_memory_real.json")
            src = "sql"
        else:
            res = run_pipeline(use_llm=use_llm)
            src = "synthetic"
        _STRAT_STATE["result"] = res
        return {"ok": True, "source": src, "summary": {
            "n_assets": res["n_assets"], "n_templates": res["n_templates"],
            "windows": len(res["log"]),
            "memory": res["memory"].stats(),
        }}
    finally:
        _STRAT_STATE["running"] = False


@app.get("/api/strategy/memory")
def api_strategy_memory():
    s = _STRAT_STATE.get("result")
    if not s:
        return {"success": [], "fail": []}
    mem = s["memory"]
    def _pack(e):
        return {"strategy": e.strategy_name, "regime": e.regime,
                "outcome": e.outcome, "sharpe": round(e.metrics.get("sharpe", 0), 3),
                "reason": e.reason, "signal": e.signal}
    return {"success": [_pack(e) for e in mem.successes[-20:]],
            "fail": [_pack(e) for e in mem.failures[-20:]]}


# --------------------------------------------------------------------------- #
# 主页：对话式生成（因子 / 策略）→ 回测 → 存经验库
# --------------------------------------------------------------------------- #
_CHAT_HIST: dict = {}


def _chat_llm(system: str, user: str, max_tokens: int = 800) -> str:
    """调用 DeepSeek,失败返回空串(由调用方兜底)。"""
    import os as _os
    api_key = _os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.3, max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


def _chat_handle_strategy(text: str, md) -> dict:
    """生成策略 → 回测 → 入库。返回 {html, reply}。"""
    from strategy_backtest.step2_template_context.strategy_generator import generate_strategies
    from strategy_backtest.step3_backtest_engine.backtest_report import backtest_template
    strategies = generate_strategies(text, md=md, n=3)
    if not strategies:
        return {"html": "<div class='t'>未能生成策略，请换个说法。</div>", "reply": "未能生成策略"}
    rows = ""
    saved = []
    for tp in strategies:
        try:
            r = backtest_template(tp, md, periods_per_year=252)
            m = r["metrics"]
            _store.add_strategy(tp.id, tp.name, tp.signal, category=tp.category,
                                direction=tp.direction, description=f"对话生成: {text}",
                                metrics=m, report=r, n_periods=r["n_periods"])
            saved.append(tp.id)
        except Exception:
            continue
        rows += (f"<tr><td class='num'>{tp.id}</td><td>{tp.name}</td><td><code>{tp.signal[:55]}</code></td>"
                 f"<td class='num' style='color:{'var(--up)' if m['sharpe']>=0 else 'var(--down)'}'>{m['sharpe']:.2f}</td>"
                 f"<td class='num' style='color:{'var(--up)' if m['total_return']>=0 else 'var(--down)'}'>{m['total_return']*100:.1f}%</td>"
                 f"<td class='num'>{m['max_drawdown']*100:.1f}%</td></tr>")
    html = ("<div class='t'>已生成 <b>" + str(len(strategies)) + "</b> 个策略并在 30min CSI 数据上完成回测：</div>"
            "<table><thead><tr><th>ID</th><th>名称</th><th>信号</th><th>Sharpe</th><th>总收益</th><th>回撤</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            + (f"<div class='saved'>✓ 已存入策略库: {', '.join(saved)}</div>" if saved else ""))
    return {"html": html, "reply": f"已生成 {len(strategies)} 个策略并入库"}


def _chat_handle_factor(text: str, md) -> dict:
    """生成因子 → 完整诊断(IC/ICIR/ave|p|/冗余) → LLM解释 → 入库。返回 {html, reply}。"""
    from FACTOR.step2_factor_mining.llm_proposer import LLMProposer
    from FACTOR.step2_factor_mining.evaluation import factor_diagnostics
    proposer = LLMProposer(LLMConfig(fallback="template", seed=0))
    formulas = proposer.propose(text, 3, ctx="用户想要一个因子")
    fallback = ["CsRank(Div(Sub($close,Delay($close,20)),Delay($close,20)))",
                "Neg(CsRank(Std($returns,20)))",
                "CsRank(Sub($close,$vwap))",
                "Neg(CsRank($returns))",
                "CsRank(TsRank($close,20))"]
    lib_formulas = [f["formula"] for f in _store.list_factors(limit=500)]
    rows = ""
    saved = []
    rejected = []
    seen = set()
    for f in (list(formulas) + fallback):
        if not f or f in seen:
            continue
        seen.add(f)
        try:
            sig = ExpressionEngine().evaluate(f, md)
            _sig = Signal(f, sig.values)
            diag = factor_diagnostics(_sig, md.target,
                                      library_formulas=lib_formulas,
                                      engine=ExpressionEngine(), md=md,
                                      corr_threshold=0.8)
        except Exception:
            continue
        if diag["is_redundant"]:
            rejected.append((f, diag["max_corr"]))
            continue
        lib_formulas.append(f)
        fid = f"F{abs(hash(f))%100000:05d}"
        expl = ""
        try:
            expl = _chat_llm(
                "你是量化因子研究员。用 2-3 句中文解释因子公式的含义、交易逻辑和适用场景。",
                f"公式: {f}\nIC={diag['ic']:.4f} ICIR={diag['icir']:.3f} ave|p|={diag['ave_p']:.4f}")
        except Exception:
            pass
        _store.add_factor(fid, f, ic=diag["ic"], icir=diag["icir"],
                          max_corr=diag["max_corr"], ave_p=diag["ave_p"],
                          source="llm", name=f"对话因子", note=f"用户想法: {text}",
                          explanation=expl)
        saved.append(fid)
        p_color = "var(--up)" if diag["ave_p"] < 0.05 else "var(--text-dim)"
        rows += (f"<tr><td class='num'>{fid}</td><td><code>{f}</code></td>"
                 f"<td class='num' style='color:{'var(--up)' if diag['ic']>=0 else 'var(--down)'}'>{diag['ic']:.4f}</td>"
                 f"<td class='num'>{diag['icir']:.3f}</td>"
                 f"<td class='num' style='color:{p_color}'>{diag['ave_p']:.4f}</td>"
                 f"<td class='num'>{diag['max_corr']:.2f}</td></tr>")
        if len(saved) >= 3:
            break
    rejected_note = ""
    if rejected:
        rejected_note = ("<div class='t' style='color:var(--warn);margin-top:6px'>"
                         f"跳过 {len(rejected)} 个与库内因子高度相关(≥0.8)的候选，避免相关性红海</div>")
    if not rows:
        return {"html": "<div class='t'>未能生成合格因子。</div>" + rejected_note, "reply": "未能生成因子"}
    html = ("<div class='t'>已生成因子并完成诊断（IC / ICIR / ave|p| / maxCorr）：</div>"
            "<table><thead><tr><th>ID</th><th>公式</th><th>IC</th><th>ICIR</th><th>ave|p|</th><th>maxCorr</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            + (f"<div class='saved'>✓ 已存入因子库: {', '.join(saved)}</div>" if saved else "")
            + rejected_note)
    return {"html": html, "reply": f"已生成 {len(saved)} 个因子并入库"}


def _chat_handle_query(text: str) -> dict:
    """查询记忆库。返回 {html, reply}。"""
    t = text
    if "策略库" in t or "策略" in t and "因子" not in t:
        ss = _store.list_strategies(limit=8)
        if not ss:
            return {"html": "<div class='t'>策略库目前为空。</div>", "reply": "策略库为空"}
        rows = "".join(
            f"<tr><td class='num'>{s['id']}</td><td>{s['name']}</td>"
            f"<td class='num' style='color:{'var(--up)' if s['sharpe']>=0 else 'var(--down)'}'>{s['sharpe']:.2f}</td>"
            f"<td class='num' style='color:{'var(--up)' if s['total_return']>=0 else 'var(--down)'}'>{s['total_return']*100:.1f}%</td></tr>"
            for s in ss)
        return {"html": "<div class='t'>策略库 Top 8（按 Sharpe）：</div>"
                        "<table><thead><tr><th>ID</th><th>名称</th><th>Sharpe</th><th>总收益</th></tr></thead>"
                        f"<tbody>{rows}</tbody></table>", "reply": "策略库查询完成"}
    if "因子库" in t or "因子" in t:
        fs = _store.list_factors(limit=8)
        if not fs:
            return {"html": "<div class='t'>因子库目前为空。</div>", "reply": "因子库为空"}
        rows = "".join(
            f"<tr><td class='num'>{f['id']}</td><td><code>{f['formula'][:50]}</code></td>"
            f"<td class='num' style='color:{'var(--up)' if f['ic']>=0 else 'var(--down)'}'>{f['ic']:.4f}</td></tr>"
            for f in fs)
        return {"html": "<div class='t'>因子库 Top 8（按 |IC|）：</div>"
                        "<table><thead><tr><th>ID</th><th>公式</th><th>IC</th></tr></thead>"
                        f"<tbody>{rows}</tbody></table>", "reply": "因子库查询完成"}
    if "经验" in t:
        exps = _store.list_strategy_experience(limit=6)
        if not exps:
            return {"html": "<div class='t'>策略经验库目前为空。</div>", "reply": "经验库为空"}
        rows = "".join(
            f"<tr><td>{e['strategy_name']}</td><td><span class='pill {'up' if e['outcome']=='success' else 'down'}'>{e['outcome']}</span></td>"
            f"<td>{e['regime']}</td><td class='num'>{e['sharpe']:.2f}</td></tr>"
            for e in exps)
        return {"html": "<div class='t'>最近策略经验：</div>"
                        "<table><thead><tr><th>策略</th><th>结果</th><th>情境</th><th>Sharpe</th></tr></thead>"
                        f"<tbody>{rows}</tbody></table>", "reply": "经验库查询完成"}
    return {"html": "<div class='t'>我可以：生成策略 / 生成因子 / 查询因子库、策略库、经验库。直接描述你的想法即可。</div>",
            "reply": "请描述你的需求"}


@app.post("/chat")
def chat(body: dict = None):
    """LLM 对话：意图识别 → 生成/查询 → 返回 HTML 回复。"""
    import json as _json
    if body is None:
        raise HTTPException(400, "缺少请求体")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "请输入内容")
    if len(text) > 500:
        text = text[:500]

    # 数据懒加载
    md = None
    try:
        md = _load_real_md("2024-01-01", "2026-08-28", table="bars_30m")
    except Exception:
        md = None
    if md is None:
        data_cfg, _, _ = _default_cfgs()
        try:
            md = get_data_source(data_cfg).load(data_cfg)
        except Exception:
            md = None

    # 意图识别（LLM 或规则兜底）
    intent = "query"
    _strategy_kw = ("策略", "轮动", "做多", "做空", "动量", "反转", "低波",
                    "趋势", "跟随", "金叉", "组合", "选股", "持仓", "买卖")
    _factor_kw = ("因子", "指标", "alpha", "阿尔法", "信号公式")
    if md is not None:
        llm_ans = _chat_llm(
            "你是策略助手。判断用户意图，只输出一个词：strategy（要生成策略）/ factor（要生成因子）/ query（查询库或闲聊）。",
            text)
        if llm_ans in ("strategy", "factor", "query"):
            intent = llm_ans
        # 规则修正：显式"因子"且无交易词 → factor；显式交易词且无"因子" → strategy
        if any(k in text for k in ("看看", "查看", "查询", "有什么", "多少", "列表", "一览")) or \
           any(k in text for k in ("因子库", "策略库", "经验库", "记忆库", "经验")):
            intent = "query"
        elif "因子" in text and not any(k in text for k in ("做多", "做空", "轮动", "选股", "持仓")):
            intent = "factor"
        elif any(k in text for k in _strategy_kw) and "因子" not in text:
            intent = "strategy"
    else:
        if "因子" in text:
            intent = "factor"
        elif any(k in text for k in _strategy_kw):
            intent = "strategy"
        else:
            intent = "query"

    try:
        if intent == "strategy" and md is not None:
            res = _chat_handle_strategy(text, md)
        elif intent == "factor" and md is not None:
            res = _chat_handle_factor(text, md)
        else:
            res = _chat_handle_query(text)
    except Exception as e:
        res = {"html": f"<div class='t'>处理失败: {e}</div>", "reply": "处理失败"}

    return {"reply": res.get("reply", ""), "html": res.get("html", ""), "intent": intent}
@app.post("/generate")
def generate(kind: str = Form("strategy"), text: str = Form(...)):
    """主页对话框：用户输入想法 → 生成因子或策略 → 回测 → 存入对应经验库。"""
    from fastapi.responses import RedirectResponse
    if not text or not text.strip():
        raise HTTPException(400, "请输入想法")
    kind = "factor" if kind == "factor" else "strategy"

    # 数据：优先真实 30min CSI，否则合成兜底
    md = _load_real_md("2024-01-01", "2026-08-28", table="bars_30m")
    src = "sql" if md is not None else "synthetic"
    if md is None:
        data_cfg, _, _ = _default_cfgs()
        md = get_data_source(data_cfg).load(data_cfg)

    result = {"kind": kind, "text": text.strip(), "source": src,
              "factors": [], "strategies": [], "saved": [], "error": ""}
    try:
        if kind == "factor":
            # 因子：用 LLM 生成候选公式 → 求值 → 回测验证 IC → 入库
            from FACTOR.step1_data_ingestion.spec import LLMConfig as _LLMConfig
            from FACTOR.step2_factor_mining.llm_proposer import LLMProposer as _Proposer
            from FACTOR.step2_factor_mining.evaluation import ic as _ic_fn
            proposer = _Proposer(_LLMConfig(fallback="template", seed=0))
            formulas = proposer.propose(text.strip(), 3, ctx="用户想要一个因子")
            eng = ExpressionEngine()
            for f in formulas[:3]:
                try:
                    sig = eng.evaluate(f, md)
                    icv = float(np.nan_to_num(_ic_fn(Signal(f, sig.values), md.target), nan=0.0, copy=True))
                except Exception:
                    continue
                # 相关性校验（与库内因子）
                from FACTOR.step1_data_ingestion.spec import Signal as _Sig
                from FACTOR.step2_factor_mining.evaluation import correlation as _corr
                corr_ok = True
                for libf in _store.list_factors():
                    try:
                        lsig = eng.evaluate(libf["formula"], md)
                        r = abs(_corr(_Sig(f, sig.values), _Sig(libf["formula"], lsig.values)))
                        if r > 0.8:
                            corr_ok = False
                            break
                    except Exception:
                        continue
                if not corr_ok:
                    continue
                fid = f"F{abs(hash(f))%100000:05d}"
                _store.add_factor(fid, f, ic=icv, icir=0.0, source="llm",
                                  name=f"用户因子-{text.strip()[:10]}",
                                  note=f"用户想法: {text.strip()}")
                result["factors"].append({"id": fid, "formula": f, "ic": round(icv, 4)})
                result["saved"].append(f"因子 {fid} 已入库")
        else:
            # 策略：生成策略模板 → 回测 → 入库
            from strategy_backtest.step2_template_context.strategy_generator import generate_strategies
            from strategy_backtest.step3_backtest_engine.backtest_report import backtest_template
            strategies = generate_strategies(text.strip(), md=md, n=3)
            for tp in strategies:
                try:
                    r = backtest_template(tp, md, periods_per_year=252)
                    m = r["metrics"]
                except Exception as e:
                    continue
                sid = tp.id
                _store.add_strategy(sid, tp.name, tp.signal, category=tp.category,
                                    direction=tp.direction,
                                    description=f"用户想法: {text.strip()}",
                                    metrics=m, report=r, n_periods=r["n_periods"])
                result["strategies"].append({"id": sid, "name": tp.name,
                                             "signal": tp.signal,
                                             "metrics": m})
                result["saved"].append(f"策略 {sid} 已入库")
    except Exception as e:
        result["error"] = str(e)
    _GEN_STATE["result"] = result
    return RedirectResponse(url="/?result=1", status_code=303)
def _metric_card(label: str, value: str, color: str = "#201e19") -> str:
    return (f"<div class='mcard'><div class='mlabel'>{label}</div>"
            f"<div class='mvalue' style='color:{color}'>{value}</div></div>")


def _panel(title: str, inner: str) -> str:
    """带渐变标题栏的面板（Wind 终端式）。"""
    return (f"<div class='panel'><div class='bar'><span class='dot'></span>{title}</div>"
            f"<div class='body'>{inner}</div></div>")


def _gen_html() -> str:
    state = _GEN_STATE.get("result")
    if not state:
        body = f"""
        <h1>策略生成 + 标准回测</h1>
        <p>输入你的策略想法（自然语言），系统用 DeepSeek 把它翻译成可回测的信号公式，
           立即在真实 30 分钟 CSI 数据上跑完整回测，输出 Sharpe/回撤/胜率/IC 报告。</p>
        {_panel("策略生成", """
          <form method="post" action="/generator/run">
            <textarea name="text" rows="4" style="width:100%"
              placeholder="例：低波动股票轮动，熊市防御，持有流动性最好的几只">低波动股票轮动，熊市防御</textarea><br>
            <button type="submit">生成并回测</button>
          </form>
          <p><b>内置示例</b>：
            <button type="button" class="ghost" onclick="document.querySelector('textarea').value='趋势跟随，均线金叉做多'">趋势跟随</button>
            <button type="button" class="ghost" onclick="document.querySelector('textarea').value='做多低波动，做空高波动'">低波 vs 高波</button>
            <button type="button" class="ghost" onclick="document.querySelector('textarea').value='流动性因子，买成交最活跃的'">流动性</button>
          </p>
        """)}"""
        return _PAGE_FRAME("策略生成器 · FactorMiner", "/generator", body)

    strategies = state.get("strategies", [])
    reports = state.get("reports", [])
    src = state.get("source", "synthetic")
    cards = "".join(
        f"<h3>策略 {i+1}: {s['name']} <span class='pill'>{s['category']}</span></h3>"
        f"<p><code>{s['signal']}</code> · 方向={s['direction']}</p>"
        for i, s in enumerate(strategies))

    report_blocks = ""
    for i, r in enumerate(reports):
        m = r["metrics"]
        charts = (_svg_line(r["equity_curve"], color="#3b82f6",
                            title=f"净值曲线 ({r['label']})") +
                  _svg_line(r["drawdown_curve"], color="#2ebd85",
                            title=f"回撤曲线 ({r['label']})"))
        yearly_rows = "".join(
            f"<tr><td class='num'>{y}</td><td class='num' style='color:{'var(--down)' if v<0 else 'var(--up)'}'>{v*100:.2f}%</td></tr>"
            for y, v in r["yearly"].items()) or "<tr><td colspan=2>（无分年数据）</td></tr>"
        seg_rows = "".join(
            f"<tr><td class='num'>{s['start']}-{s['end']}</td><td class='num' style='color:{'var(--down)' if s['return']<0 else 'var(--up)'}'>{s['return']*100:.2f}%</td><td class='num'>{s['max_dd']*100:.2f}%</td></tr>"
            for s in r["segments"])
        err_html = f"<p style='color:var(--down)'>回测出错: {r.get('error','')}</p>" if r.get("error") else ""
        metric_cards = "".join([
            _metric_card('Sharpe', f"{m['sharpe']:.2f}", 'var(--up)' if m['sharpe']>=0 else 'var(--down)'),
            _metric_card('年化收益', f"{m['annualized']*100:.2f}%", 'var(--up)' if m['annualized']>=0 else 'var(--down)'),
            _metric_card('总收益', f"{m['total_return']*100:.2f}%", 'var(--up)' if m['total_return']>=0 else 'var(--down)'),
            _metric_card('最大回撤', f"{m['max_drawdown']*100:.2f}%", 'var(--warn)'),
            _metric_card('胜率', f"{m['win_rate']*100:.1f}%"),
            _metric_card('rank IC', f"{m['rank_ic']:.4f}"),
        ])
        report_blocks += _panel(
            f"回测报告: {r['label']} <span class='pill'>{r['n_periods']} 期 · {r['direction']}</span>",
            f"""{err_html}
          <div class="mcards">{metric_cards}</div>
          <div class="grid">{charts}</div>
          <h4>分年收益</h4>
          <table><thead><tr><th>年份</th><th>收益</th></tr></thead><tbody>{yearly_rows}</tbody></table>
          <h4>分段表现（每 50 期）</h4>
          <table><thead><tr><th>区间</th><th>收益</th><th>最大回撤</th></tr></thead><tbody>{seg_rows}</tbody></table>""")

    body = f"""
    <h1>策略生成 + 标准回测</h1>
    <p>数据源 <span class='pill'>{'真实 30min CSI' if src=='sql' else '合成兜底'}</span></p>
    {_panel("重新生成", """
      <form method="post" action="/generator/run">
        <textarea name="text" rows="2" style="width:100%"
          placeholder="输入新的策略想法...">{state.get('text','')}</textarea><br>
        <button type="submit">重新生成并回测</button>
      </form>
    """)}
    <h2>生成策略</h2>
    {cards}
    {report_blocks}"""
    return _PAGE_FRAME("策略生成器 · FactorMiner", "/generator", body)


@app.get("/generator", response_class=HTMLResponse)
def generator_page():
    return _gen_html()


@app.post("/generator/run")
def generator_run(text: str = Form(...)):
    if _GEN_STATE["running"]:
        raise HTTPException(409, "已在运行中")
    if not text or not text.strip():
        raise HTTPException(400, "请输入策略描述")
    _GEN_STATE["running"] = True
    try:
        # 数据：优先真实 30min CSI，否则合成兜底
        md = _load_real_md("2024-01-01", "2026-08-28", table="bars_30m")
        src = "sql" if md is not None else "synthetic"
        if md is None:
            data_cfg, _, _ = _default_cfgs()
            md = get_data_source(data_cfg).load(data_cfg)

        strategies = generate_strategies(text.strip(), md=md, n=3)
        reports = []
        for tp in strategies:
            try:
                r = backtest_template(tp, md, periods_per_year=252)
                r["label"] = f"{tp.name} ({tp.id})"
                reports.append(r)
            except Exception as e:
                reports.append({"label": f"{tp.name} ({tp.id})", "metrics": {
                    "sharpe": 0, "annualized": 0, "total_return": 0,
                    "max_drawdown": 0, "win_rate": 0, "rank_ic": 0},
                    "equity_curve": [], "drawdown_curve": [],
                    "yearly": {}, "segments": [], "n_periods": 0,
                    "direction": tp.direction, "error": str(e)})
        _GEN_STATE["result"] = {
            "text": text.strip(), "source": src,
            "strategies": [{"name": tp.name, "signal": tp.signal,
                            "category": tp.category, "direction": tp.direction}
                           for tp in strategies],
            "reports": reports,
        }
        return {"ok": True, "source": src, "n_strategies": len(strategies),
                "reports": reports}
    finally:
        _GEN_STATE["running"] = False
