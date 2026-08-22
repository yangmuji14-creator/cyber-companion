/* First-run setup: model connection, then the beginner-friendly persona guide. */

const byId = (id) => document.getElementById(id);
let helperTarget = null;
let helperBound = false;

const CORE_FIELDS = [
  {
    key: "system_prompt",
    label: "系统提示词",
    hint: "写整体行为规则：它应该怎样回应、遵守什么边界。适合放稳定的原则。",
    placeholder: "例如：你是一个自然、真诚的聊天伙伴，先回应对方最在意的内容。",
  },
  {
    key: "output_examples",
    label: "输出示例",
    hint: "写几组它常用的说法，让模型学会语气、长度和口头禅。每组可以用“对方说 / 你说”。",
    placeholder: "对方说：今天有点累\n你说：辛苦啦，先歇一会儿。",
  },
  {
    key: "persona_prompt",
    label: "人设提示词",
    hint: "写它是谁：名字、性格、关系、兴趣、生活背景。这里更像角色小传。",
    placeholder: "例如：你叫小可爱，温柔活泼，喜欢动漫和游戏，和对方是关系亲近的朋友。",
  },
];

function payload() {
  return {
    provider: byId("bootstrap-provider")?.value || "",
    api_key: byId("bootstrap-api-key")?.value.trim() || "",
    model_name: byId("bootstrap-model")?.value.trim() || "",
    base_url: byId("bootstrap-base-url")?.value.trim() || "",
  };
}

function renderCoreForm(container, values, prefix) {
  if (!container) return;
  container.replaceChildren();
  for (const meta of CORE_FIELDS) {
    const field = document.createElement("label");
    field.className = "bootstrap-persona-field";
    const title = document.createElement("span");
    title.textContent = meta.label;
    const textarea = document.createElement("textarea");
    textarea.id = `${prefix}-${meta.key}`;
    textarea.dataset.personaKey = meta.key;
    textarea.rows = 4;
    textarea.placeholder = meta.placeholder;
    textarea.value = values?.[meta.key] || "";
    const hint = document.createElement("small");
    hint.textContent = meta.hint;
    field.append(title, textarea, hint);
    container.appendChild(field);
  }
}

function readCoreForm(prefix) {
  const result = {};
  for (const meta of CORE_FIELDS) result[meta.key] = byId(`${prefix}-${meta.key}`)?.value.trim() || "";
  return result;
}

function openHelper(target) {
  helperTarget = target;
  byId("persona-helper-overlay").hidden = false;
  byId("helper-name")?.focus();
}

function closeHelper() {
  byId("persona-helper-overlay").hidden = true;
  helperTarget = null;
}

function generateHelperValues() {
  const name = byId("helper-name")?.value.trim() || "小可爱";
  const relation = byId("helper-relation")?.value.trim() || "关系亲近的朋友";
  const personality = byId("helper-personality")?.value.trim() || "温柔、活泼、偶尔傲娇";
  const style = byId("helper-style")?.value.trim() || "短句、自然、偶尔撒娇";
  const background = byId("helper-background")?.value.trim() || "喜欢动漫和游戏，会主动分享日常";
  return {
    system_prompt: `你是一个真实、自然的聊天伙伴。保持角色一致，用${style}的方式回应，先回应对方最在意的内容，再自然延伸话题。不要像客服，也不要解释设定。`,
    output_examples: `对方说：今天有点累\n你说：辛苦啦，先歇一会儿。要不要跟我说说今天发生了什么？\n\n对方说：我刚看到一只猫\n你说：在哪里看到的？可爱吗，突然有点想看你拍的照片了。`,
    persona_prompt: `你叫${name}，性格是${personality}。你们是${relation}。${background}。你说话${style}，有自己的情绪和生活，也会认真记住对方在意的事情。`,
  };
}

function applyHelperValues(values) {
  const prefix = helperTarget === "bootstrap" ? "bootstrap-persona" : "persona";
  for (const meta of CORE_FIELDS) {
    const input = byId(`${prefix}-${meta.key}`);
    if (input) input.value = values[meta.key] || "";
  }
  closeHelper();
}

function bindHelper() {
  if (helperBound) return;
  helperBound = true;
  byId("persona-helper-close")?.addEventListener("click", closeHelper);
  byId("persona-helper-cancel")?.addEventListener("click", closeHelper);
  byId("persona-helper-generate")?.addEventListener("click", () => applyHelperValues(generateHelperValues()));
  byId("bootstrap-persona-helper")?.addEventListener("click", () => openHelper("bootstrap"));
  byId("btn-persona-helper")?.addEventListener("click", () => openHelper("settings"));
}

async function discoverModels(result, modelInput) {
  try {
    const response = await fetch("/api/bootstrap/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url: byId("bootstrap-base-url")?.value.trim(), api_key: byId("bootstrap-api-key")?.value.trim() }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || "拉取模型失败");
    const current = modelInput.value;
    const datalist = byId("bootstrap-model-options");
    datalist?.replaceChildren();
    for (const model of data.models || []) {
      const option = document.createElement("option");
      option.value = model;
      datalist?.appendChild(option);
    }
    modelInput.disabled = false;
    if (current && [...modelInput.options].some((option) => option.value === current)) modelInput.value = current;
    result.textContent = data.message || "已拉取模型";
    result.className = "bootstrap-result success";
    return true;
  } catch (error) {
    modelInput.disabled = false;
    byId("bootstrap-model-options")?.replaceChildren();
    result.textContent = `${error.message || "拉取模型失败"}，也可以手动填写模型 ID。`;
    result.className = "bootstrap-result error";
    return false;
  }
}

export async function initBootstrap() {
  bindHelper();
  let status;
  try {
    const response = await fetch("/api/bootstrap/status");
    if (!response.ok) return;
    status = await response.json();
  } catch {
    return;
  }
  if (!status.needs_setup && !status.needs_persona_setup) return;

  const overlay = byId("bootstrap-overlay");
  const form = byId("bootstrap-form");
  const modelStep = byId("bootstrap-model-step");
  const personaStep = byId("bootstrap-persona-step");
  const provider = byId("bootstrap-provider");
  const providerDesc = byId("bootstrap-provider-desc");
  const model = byId("bootstrap-model");
  const baseUrl = byId("bootstrap-base-url");
  const apiKey = byId("bootstrap-api-key");
  const testButton = byId("bootstrap-test");
  const completeButton = byId("bootstrap-complete");
  const result = byId("bootstrap-result");
  const personaResult = byId("bootstrap-persona-result");
  const personaComplete = byId("bootstrap-persona-complete");
  const personaDefaults = status.persona_defaults || {};

  const catalogResponse = await fetch("/api/bootstrap/providers");
  const catalogData = await catalogResponse.json();
  const providers = catalogData.providers || [];
  const providerMap = new Map(providers.map((item) => [item.key, item]));
  provider.replaceChildren();
  for (const item of providers) {
    const option = document.createElement("option");
    option.value = item.key;
    option.textContent = item.label;
    provider.appendChild(option);
  }

  const applyProvider = () => {
    const spec = providerMap.get(provider.value);
    if (!spec) return;
    providerDesc.textContent = spec.description;
    baseUrl.value = spec.base_url;
    model.value = "";
    model.placeholder = "先点击“拉取模型”，再从列表选择";
    model.disabled = false;
    completeButton.disabled = true;
    result.textContent = "";
    result.className = "bootstrap-result";
  };
  provider.addEventListener("change", applyProvider);
  for (const input of [apiKey, model, baseUrl]) {
    input.addEventListener("input", () => {
      completeButton.disabled = true;
      result.textContent = "";
      result.className = "bootstrap-result";
    });
  }
  applyProvider();
  renderCoreForm(byId("bootstrap-persona-form"), personaDefaults, "bootstrap-persona");
  overlay.hidden = false;
  bindHelper();

  const showPersonaStep = () => {
    modelStep.hidden = true;
    personaStep.hidden = false;
    byId("bootstrap-title").textContent = "定义你的陪伴者";
    const topSubtitle = document.querySelector(".bootstrap-panel > .bootstrap-subtitle");
    if (topSubtitle) topSubtitle.hidden = true;
    byId("bootstrap-persona-system_prompt")?.focus();
  };

  if (!status.needs_setup) showPersonaStep();
  else apiKey.focus();

  testButton.addEventListener("click", async () => {
    if (!apiKey.value.trim() || !baseUrl.value.trim()) {
      result.textContent = "请先填写 API 密钥和地址。";
      result.className = "bootstrap-result error";
      return;
    }
    testButton.disabled = true;
    completeButton.disabled = true;
    result.textContent = "正在拉取模型…";
    result.className = "bootstrap-result pending";
    await discoverModels(result, model);
    testButton.disabled = false;
    if (model.value.trim()) {
      result.textContent += " 请选择一个模型，保存时会自动测试连接。";
      completeButton.disabled = true;
    }
  });

  model.addEventListener("change", () => { completeButton.disabled = !model.value.trim(); });
  model.addEventListener("input", () => { completeButton.disabled = !model.value.trim(); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (modelStep.hidden || completeButton.disabled) return;
    completeButton.disabled = true;
    result.textContent = "正在测试连接…";
    result.className = "bootstrap-result pending";
    try {
      const response = await fetch("/api/bootstrap/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) throw new Error(data.message || "连接测试失败");
      result.textContent = data.message || "连接成功";
      result.className = "bootstrap-result success";
      const saveResponse = await fetch("/api/bootstrap/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      if (!saveResponse.ok) {
        const saveData = await saveResponse.json().catch(() => ({}));
        throw new Error(saveData.error || "模型保存失败");
      }
      if (status.needs_persona_setup) showPersonaStep();
      else { overlay.hidden = true; return; }
    } catch (error) {
      result.textContent = error.message || "连接失败，请稍后重试";
      result.className = "bootstrap-result error";
      completeButton.disabled = false;
    }
  });

  personaComplete.addEventListener("click", async () => {
    personaComplete.disabled = true;
    personaResult.textContent = "正在保存人设…";
    personaResult.className = "bootstrap-result pending";
    try {
      const response = await fetch("/api/bootstrap/persona", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readCoreForm("bootstrap-persona")),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "保存人设失败");
      personaResult.textContent = "人设已保存，马上开始聊天。";
      personaResult.className = "bootstrap-result success";
      overlay.hidden = true;
    } catch (error) {
      personaResult.textContent = error.message || "保存人设失败，请稍后重试";
      personaResult.className = "bootstrap-result error";
      personaComplete.disabled = false;
    }
  });
}
