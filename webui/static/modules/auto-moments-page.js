/* ===== auto-moments-page.js — 朋友圈 AI 自动发布子页 =====
 *
 * 配置 AI 定时为指定角色发布一条朋友圈动态：
 *  - 启用开关
 *  - 选择发布角色（persona）
 *  - 发布间隔（分钟）
 *  - 活跃时间段（起止小时）
 *  - 手动「立即发布一条」即时触发
 *
 * 文案默认由 LLM 实时生成（无模型时回退角色风格模板）。
 *
 * 后端端点：
 *  - GET/PUT /api/moments/auto/config
 *  - POST /api/moments/auto/publish
 * 渲染安全：动态文本一律 textContent，防止 XSS。
 * 入口：renderAutoMomentsPage(container)
 */

import { el } from "./state.js";
import { toast, userFacingError } from "./ui.js";

const CONTAINER_SEL = "#tab-content-auto-moments, #moments-auto-container";

async function apiJson(url, opts = {}) {
  const res = await fetch(url, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function wrapField(labelText) {
  const wrap = el("label", "am-field");
  const span = el("span");
  span.textContent = labelText;
  wrap.appendChild(span);
  return wrap;
}

function hourSelect(value, placeholder) {
  const wrap = wrapField(placeholder);
  const select = document.createElement("select");
  for (let h = 0; h <= 23; h += 1) {
    const opt = document.createElement("option");
    opt.value = String(h);
    opt.textContent = `${h} 点`;
    if (String(h) === String(value)) opt.selected = true;
    select.appendChild(opt);
  }
  wrap.appendChild(select);
  return wrap;
}

async function refresh(target) {
  try {
    const data = await apiJson("/api/moments/auto/config");
    const cfg = data.config || {};
    const personas = data.personas || [];
    target.innerHTML = "";

    const title = el("h3", "am-title");
    title.textContent = "朋友圈 AI 自动发布";
    target.appendChild(title);

    const desc = el("p", "am-desc");
    desc.textContent = "让某位角色按间隔自动发布朋友圈，文案由 AI 生成。";
    target.appendChild(desc);

    // 启停
    const enabledWrap = el("label", "am-check");
    const enabledInput = document.createElement("input");
    enabledInput.type = "checkbox";
    enabledInput.checked = !!cfg.enabled;
    const enabledSpan = el("span");
    enabledSpan.textContent = "启用自动发布";
    enabledWrap.appendChild(enabledInput);
    enabledWrap.appendChild(enabledSpan);
    target.appendChild(enabledWrap);

    // 角色
    const personaWrap = wrapField("发布角色");
    const personaSelect = document.createElement("select");
    const noneOpt = document.createElement("option");
    noneOpt.value = "";
    noneOpt.textContent = "（请选择角色）";
    if (!cfg.persona_id) noneOpt.selected = true;
    personaSelect.appendChild(noneOpt);
    for (const p of personas) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      if (p.id === cfg.persona_id) opt.selected = true;
      personaSelect.appendChild(opt);
    }
    personaWrap.appendChild(personaSelect);
    target.appendChild(personaWrap);

    // 间隔
    const intervalWrap = wrapField("发布间隔（分钟）");
    const intervalInput = document.createElement("input");
    intervalInput.type = "number";
    intervalInput.min = "5";
    intervalInput.step = "5";
    intervalInput.value = cfg.interval_minutes || 180;
    intervalWrap.appendChild(intervalInput);
    target.appendChild(intervalWrap);

    // 活跃时间段
    const winWrap = el("div", "am-window");
    const winLabel = el("span", "am-window-label");
    winLabel.textContent = "活跃时间段（仅此时段内自动发布）";
    winWrap.appendChild(winLabel);
    const winRow = el("div", "am-window-row");
    const startSel = hourSelect(cfg.active_start, "开始");
    const endSel = hourSelect(cfg.active_end, "结束");
    winRow.appendChild(startSel);
    winRow.appendChild(endSel);
    winWrap.appendChild(winRow);
    target.appendChild(winWrap);

    // 按钮
    const btns = el("div", "am-btns");
    const publish = el("button", "ghost-btn");
    publish.type = "button";
    publish.textContent = "立即发布一条";
    publish.title = "无视间隔立即生成并发布一条（需启用且选了角色）";
    publish.addEventListener("click", async () => {
      try {
        await apiJson("/api/moments/auto/publish", { method: "POST" });
        toast("已发布一条 AI 动态");
      } catch (e) {
        toast(userFacingError(e, "发布失败"));
      }
    });
    btns.appendChild(publish);
    const save = el("button", "primary-btn");
    save.type = "button";
    save.textContent = "保存";
    save.addEventListener("click", async () => {
      const body = {
        enabled: enabledInput.checked,
        persona_id: personaSelect.value,
        interval_minutes: Number(intervalInput.value) || 180,
        active_start: Number(startSel.querySelector("select").value),
        active_end: Number(endSel.querySelector("select").value),
      };
      if (!body.persona_id) {
        toast("请先选择一个发布角色");
        return;
      }
      try {
        await apiJson("/api/moments/auto/config", {
          method: "PUT",
          body: JSON.stringify(body),
        });
        toast("已保存");
        await refresh(target);
      } catch (e) {
        toast(userFacingError(e, "保存失败"));
      }
    });
    btns.appendChild(save);
    target.appendChild(btns);

    if (!personas.length) {
      const hint = el("p", "am-hint");
      hint.textContent = "暂无角色可选，请先在人设设定中添加角色。";
      target.appendChild(hint);
    }
  } catch (e) {
    target.innerHTML = "";
    const err = el("div", "am-error");
    err.textContent = userFacingError(e, "自动发布配置加载失败");
    target.appendChild(err);
  }
}

/** 渲染到指定容器；若无容器则尝试 #tab-content-auto-moments / #moments-auto-container。 */
export async function renderAutoMomentsPage(container = null) {
  const target = container || document.querySelector(CONTAINER_SEL);
  if (!target) return;
  await refresh(target);
}
