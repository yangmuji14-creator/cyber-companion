<script>
  // ============================================================
  // ContactsPage.svelte — 通讯录 人设/角色花名册 + 分组详情编辑
  //
  // - 列表: GET /api/persona -> [{id,name,avatar}]
  // - 搜索过滤名字; 点行进详情子视图 (组件内状态切换)
  // - 详情: GET /api/persona/{id} -> USER_FIELDS dict
  //         GET /api/persona/{id}/advanced -> ADVANCED_FIELDS dict
  // - 分组 Tab 编辑: 一个 schema (USER_GROUPS + ADV_GROUP) 刻画每个字段
  //   控件类型 (text/number/textarea/select/range/switch/list/list-dict/json),
  //   保存只提交当前分组涉及的字段, POST /api/persona/{id} {"fields":{...}}
  // - 精简视图 (PawzoChat 风格: 顶部固定基础区 头像+名字) + 3 张核心人设卡
  //   (PersonaCard) 关 textarea 优先; 其余全部字段收进「高级/全部字段」  //   折叠区 (PersonaAdvanced, 默认收起, 手风琴按原分组收起)  //   精简卡字段在高级区不重复, 54 个字段均可完整读写。  // - 新建 POST /api/persona {id,name,description?}
  // - 删除 DELETE /api/persona/{id}
  // - 头像: POST /api/persona/{id}/avatar (multipart file) / DELETE
  // - 去聊天 goTab('chat')
  //
  // 字段类型对照后端 core/persona/models.py (权威):
  //   initiative_level/clinginess/jealous_tendency : str (高中底 -> select
  //   relationship_level : int 0-100 -> range 滑杆
  //   sticker_probability : float -> range 0-1 (百分比显示)
  //   hobby : list[dict{name,detail}] -> list-dict 两列编辑
  //   高级 dict 字段 (identity_anchor/speaking_style/...) -> json 文本区  // ============================================================
import { get, post, del, postFile } from '../lib/pages-api.js';
import { goTab } from '../lib/router.js';
import { confirmDialog } from '../lib/dialog.svelte.js';
import Avatar from '../components/Avatar.svelte';
  import Toast from '../components/Toast.svelte';
  import PersonaCard from '../components/persona/PersonaCard.svelte';
  import PersonaAdvanced from '../components/persona/PersonaAdvanced.svelte';
  import PromptAdvancedPanel from '../components/persona/PromptAdvancedPanel.svelte';
  import { PROMPT_ALL } from '../components/persona/promptFields.js';

  // ============================================================
  // 字段 schema: 分组 tab -> 字段控制描述
  // ============================================================
  const USER_GROUPS = [
    {
      id: 'basic',
      label: '基本信息',
      fields: [
        { key: 'name', label: '名字', type: 'text' },
        { key: 'age', label: '年龄', type: 'number', step: 1, min: 0 },
        { key: 'gender', label: '性别', type: 'text', placeholder: '男/女' },
        { key: 'birthday', label: '生日', type: 'text', placeholder: '如 3 月 14 日' },
        { key: 'hometown', label: '家乡', type: 'text' },
        { key: 'occupation', label: '职业', type: 'text' },
        { key: 'relationship_level', label: '关系阶段 (%)', type: 'range', min: 0, max: 100, step: 1 },
        { key: 'daily_routine', label: '日常作息', type: 'textarea' },
        { key: 'appearance', label: '外貌', type: 'textarea' },
        { key: 'background', label: '背景故事', type: 'textarea' },
      ],
    },
    {
      id: 'personality',
      label: '性格与特征',
      fields: [
        { key: 'personality', label: '性格特点', type: 'list', emptyHint: '每行一个性格标签，点「添加」新增' },
        { key: 'mbti', label: 'MBTI', type: 'text', placeholder: '如 INFP' },
        { key: 'hobbies', label: '爱好', type: 'list-dict', namePlaceholder: '爱好名称', detailPlaceholder: '补充说明（可选）' },
        { key: 'initiative_level', label: '主动程度', type: 'select', options: ['低', '中', '高'] },
        { key: 'clinginess', label: '粘人程度', type: 'select', options: ['低', '中', '高'] },
        { key: 'jealous_tendency', label: '吃醋倾向', type: 'select', options: ['低', '中', '高'] },
        { key: 'conflict_style', label: '冲突风格', type: 'textarea' },
        { key: 'affection_style', label: '示爱风格', type: 'textarea' },
        { key: 'question_tendency', label: '提问倾向', type: 'textarea' },
      ],
    },
    {
      id: 'expression',
      label: '表达与说话',
      fields: [
        { key: 'speech_rhythm', label: '语速节奏', type: 'textarea' },
        { key: 'emoji_habits', label: 'Emoji 习惯', type: 'text' },
        { key: 'catchphrases', label: '口头禅', type: 'list' },
        { key: 'filler_words', label: '语气词', type: 'list' },
        { key: 'pet_names', label: '昵称', type: 'list' },
        { key: 'nickname_for_user', label: '对我的称呼', type: 'text' },
        { key: 'happy_expression', label: '开心表达', type: 'text' },
        { key: 'sad_expression', label: '难过表达', type: 'text' },
        { key: 'angry_expression', label: '生气表达', type: 'text' },
        { key: 'jealous_expression', label: '吃醋表达', type: 'text' },
        { key: 'shy_expression', label: '害羞表达', type: 'text' },
      ],
    },
    {
      id: 'interests',
      label: '兴趣与话题',
      fields: [
        { key: 'music_taste', label: '音乐品味', type: 'textarea' },
        { key: 'movie_taste', label: '影视品味', type: 'textarea' },
        { key: 'food_preferences', label: '饮食偏好', type: 'textarea' },
        { key: 'favorite_topics', label: '喜欢的话题', type: 'list' },
        { key: 'avoided_topics', label: '回避的话题', type: 'list' },
      ],
    },
    {
      id: 'stickers',
      label: '表情包',
      fields: [
        { key: 'sticker_enabled', label: '表情包开关', type: 'switch' },
        { key: 'sticker_probability', label: '表情包概率', type: 'range', min: 0, max: 1, step: 0.01, percent: true },
        { key: 'sticker_pack', label: '表情包组', type: 'text', placeholder: '如 builtin' },
      ],
    },
  ];

  // 高级 Prompt 分组 (次级/折叠) ：字段来自 promptFields.js (单一事实来源)
  // 这些字段由 PromptAdvancedPanel 以友好分层的方式渲染, 不再平铺 raw json。
  const ADV_GROUP = {
    id: 'advanced',
    label: '高级 Prompt',
    hint: '以下字段直接影响模型行为，若不确定请保持默认',
    fields: PROMPT_ALL,
  };

  // ============================================================
  // 精简视图 (PawzoChat 风格: 默认展示的核心人设卡字段
  // 这些字段在「高级/全部字段」区中不再重复出现。  // ============================================================
  const LEAN_CARDS = [
    {
      id: 'who',
      title: '人设 · 一句话认识 TA',
      subtitle: 'TA 是谁、什么样，第一眼就知道',
      fields: [
        { key: 'background', label: '背景故事', type: 'textarea', rows: 4 },
        { key: 'personality', label: '性格标签', type: 'list', emptyHint: '每行一个性格词，点「添加」新增，如 温柔、毒舌' },
        { key: 'gender', label: '性别', type: 'text', placeholder: '男/女' },
        { key: 'age', label: '年龄', type: 'number', step: 1, min: 0 },
      ],
    },
    {
      id: 'talk',
      title: '说话与相处',
      subtitle: 'TA 怎么叫你、怎么说话',
      fields: [
        { key: 'nickname_for_user', label: '对我的称呼', type: 'text', placeholder: 'TA 怎么称呼你，如 亲爱的' },
        { key: 'catchphrases', label: '口头禅', type: 'list', emptyHint: '每行一句口头禅，点「添加」新增' },
        { key: 'speech_rhythm', label: '语速与节奏', type: 'textarea', rows: 3 },
      ],
    },
    {
      id: 'intimacy',
      title: '亲密与表情包',
      subtitle: '关系进度与表情包',
      fields: [
        { key: 'relationship_level', label: '关系阶段 (%)', type: 'range', min: 0, max: 100, step: 1 },
        { key: 'sticker_enabled', label: '表情包开关', type: 'switch' },
        { key: 'pet_names', label: '我的称呼', type: 'list', emptyHint: '你叫 TA 的昵称，每行一个' },
      ],
    },
  ];

  // 精简卡涉及的字段 key 集合 (用于从高级区剔除)
  function leanKeys() {
    const s = new Set();
    for (const c of LEAN_CARDS) for (const f of c.fields) s.add(f.key);
    return s;
  }

  // 「高级/全部字段」分片 = 原分组减去除精简卡字段 (因 name 已在顶部)
  // 高级 Prompt 字段不在此区, 由下方 PromptAdvancedPanel 以分层友好方式渲染。
  function buildAdvancedGroups() {
    const skip = leanKeys();
    skip.add('name');
    const groups = [];
    for (const g of USER_GROUPS) {
      const rest = g.fields.filter((f) => !skip.has(f.key));
      if (rest.length) groups.push({ id: g.id, label: g.label, hint: g.hint, fields: rest });
    }
    return groups;
  }

  const ADVANCED_GROUPS = buildAdvancedGroups();

  // 查字段 meta
  // ============================================================
  // 归一化: 后端值 -> 编辑值  // ============================================================
  function norm(v, meta) {
    switch (meta.type) {
      case 'list':
        if (Array.isArray(v)) return v.map((s) => String(s));
        if (typeof v === 'string' && v.trim()) return v.split('\n').map((s) => s.trim()).filter(Boolean);
        return v == null ? [] : [String(v)];
      case 'list-dict': {
        if (!Array.isArray(v)) return [];
        return v.map((x) => ({ name: x?.name || '', detail: x?.detail || '' }));
      }
      case 'json':
        // dict 类字段: 空对象 -> 空文本 否则美化 JSON
        if (v == null) return '';
        if (typeof v === 'string') return v;
        if (typeof v === 'object' && Object.keys(v).length === 0) return '';
        return JSON.stringify(v, null, 2);
      case 'prompt-dict': {
        // 友好键值表示 归一化为对象, 保留全部历史 key(不丢字段),
        // 并确保 spec.keys 均存在(供输入框绑定)。
        const spec = meta.spec || {};
        const out = {};
        if (v && typeof v === 'object') {
          for (const [k, val] of Object.entries(v)) {
            if (val != null && typeof val !== 'object') out[k] = String(val);
          }
        } else if (typeof v === 'string') {
          const first = spec.keys && spec.keys[0];
          if (first != null) out[first] = v;
        }
        for (const k of spec.keys || []) {
          if (out[k] == null) out[k] = '';
        }
        return out;
      }
      case 'dialog-list': {
        // 结构化示例对: list[{ scenario, reply:[..] }]
        if (!Array.isArray(v)) return [];
        return v.map((d) => ({
          scenario: d?.scenario || '',
          reply: Array.isArray(d?.reply) ? d.reply.map((s) => String(s)) : [],
        }));
      }
      case 'range':
        if (v == null || v === '') return meta.min ?? 0;
        return Number(v);
      case 'number':
        if (v == null || v === '') return '';
        return Number(v);
      case 'switch':
        return !!v;
      case 'select':
      case 'text':
      case 'textarea':
      default:
        return v == null ? '' : String(v);
    }
  }

  // 反归一化: 编辑值 -> 后端值
  function denorm(slot) {
    const meta = slot.meta;
    const v = slot.value;
    switch (meta.type) {
      case 'list':
        return Array.isArray(v) ? v.map((s) => String(s).trim()).filter((s) => s) : [];
      case 'list-dict':
        return Array.isArray(v)
          ? v
              .filter((r) => r && String(r.name || '').trim())
              .map((r) => {
                const name = String(r.name).trim();
                const detail = String(r.detail || '').trim();
                return detail ? { name, detail } : { name };
              })
          : [];
      case 'json': {
        if (typeof v === 'string' && v.trim()) {
          try {
            return JSON.parse(v);
          } catch {
            // 解析失败则回退到后端原始值 避免破坏数据
            return slot.orig ?? {};
          }
        }
        return slot.orig ?? {};
      }
      case 'prompt-dict': {
        // 只保留非空 key, 且与 prompt_builder 期望的 key 完全一致
        // 未知 key(历史遗留) 原样保留, 不丢字段。
        if (!v || typeof v !== 'object') return {};
        const out = {};
        for (const [k, val] of Object.entries(v)) {
          const s = String(val ?? '').trim();
          if (s) out[k] = s;
        }
        return out;
      }
      case 'dialog-list': {
        // 过滤空场景条目: 剔除空回复 保持 { scenario, reply }
        if (!Array.isArray(v)) return [];
        return v
          .filter((d) => d && String(d.scenario || '').trim())
          .map((d) => ({
            scenario: String(d.scenario).trim(),
            reply: Array.isArray(d.reply)
              ? d.reply.map((s) => String(s).trim()).filter(Boolean)
              : [],
          }));
      }
      case 'number':
        return v === '' ? undefined : Number(v);
      case 'range':
        return Number(v);
      case 'switch':
        return !!v;
      case 'select':
      case 'text':
      case 'textarea':
      default:
        return String(v ?? '');
    }
  }

  // ============================================================
  // 状态变量  // ============================================================
  let list = $state([]);
  let loading = $state(true);
  let query = $state('');
  let selected = $state(null); // persona id in detail
  let detail = $state(null); // USER_FIELDS dict
  let advanced = $state(null); // ADVANCED_FIELDS dict
  let loadingDetail = $state(false);
  let detailError = $state('');
  let saving = $state(false);
  let toast = $state(null);
  let toastTimer = null;

  // 新建弹窗
  let showCreate = $state(false);
  let newForm = $state({ id: '', name: '', description: '' });
  let creating = $state(false);

  // 表单编辑状态 { key: { meta, value, orig? } } (rune 深响应
  let form = $state({});

  let filtered = $derived(
    query.trim() ? list.filter((p) => (p.name || '').toLowerCase().includes(query.trim().toLowerCase())) : list
  );

  $effect(() => {
    loadList();
  });

  async function loadList() {
    loading = true;
    const r = await get('/api/persona');
    list = Array.isArray(r.data) ? r.data : [];
    loading = false;
  }

  function showToast(text, type = 'info') {
    toast = { text, type };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2400);
  }

  function openDetail(id) {
    selected = id;
    detailError = '';
    loadDetail();
  }

  function backToList() {
    selected = null;
    detail = null;
    advanced = null;
    form = {};
  }

  async function loadDetail() {
    if (selected == null) return;
    loadingDetail = true;
    detailError = '';
    const [b, a] = await Promise.all([
      get(`/api/persona/${selected}`),
      get(`/api/persona/${selected}/advanced`),
    ]);
    loadingDetail = false;
    if (!b.ok) {
      detailError = '加载失败，请重试';
      return;
    }
    const base = b.data && typeof b.data === 'object' ? b.data : {};
    detail = base;

    // 初始化编辑状态: 以 schema 覆盖扫描 USER/ADVANCED 字段
    const f = {};
    for (const g of USER_GROUPS) {
      for (const meta of g.fields) {
        const raw = base[meta.key];
        f[meta.key] = { meta, value: norm(raw, meta), orig: raw };
      }
    }
    if (a.ok && a.data && typeof a.data === 'object') {
      advanced = a.data;
      for (const meta of ADV_GROUP.fields) {
        const raw = a.data[meta.key];
        f[meta.key] = { meta, value: norm(raw, meta), orig: raw };
      }
    } else {
      advanced = {};
      for (const meta of ADV_GROUP.fields) {
        const raw = undefined;
        f[meta.key] = { meta, value: norm(raw, meta), orig: raw };
      }
    }
    form = f;
  }

  // 提交指定 key 涉及的字段 (精简区/高级区手风琴共用)
  async function saveFields(keys, label) {
    if (!selected || saving) return;
    saving = true;
    const fields = {};
    for (const key of keys) {
      const slot = form[key];
      if (!slot) continue;
      const val = denorm(slot);
      // 年龄为空则发 '' (后端宽松); 其余照常
      if (val === undefined) continue;
      fields[key] = val;
    }
    const r = await post(`/api/persona/${selected}`, { fields });
    saving = false;
    if (r.ok) {
      showToast(label ? `「{label}」已保存` : '已保存', 'success');
      const nameSlot = form['name'];
      if (nameSlot && fields.name !== undefined) {
        // 名字变了 -> 刷新列表
        if (String(fields.name) !== String(nameSlot.orig ?? '')) await loadList();
      }
    } else {
      showToast(r.data?.error || r.data?.detail || '保存失败', 'error');
    }
  }

  // 精简卡保存: 复用按字段过滤提交
  function saveCard(keys, label) {
    saveFields(keys, label);
  }

  // 高级区手风琴按分组保存
  function saveAdvanced(keys, label) {
    saveFields(keys, label);
  }

  // ---- 新建 ----
  async function createPersona() {
    const id = newForm.id.trim();
    const name = newForm.name.trim();
    if (!id || !name) {
      showToast('请填写角色 ID 与名字', 'error');
      return;
    }
    creating = true;
    const r = await post('/api/persona', {
      id,
      name,
      description: newForm.description.trim() || undefined,
    });
    creating = false;
    if (r.ok) {
      showToast('已创建新角色', 'success');
      showCreate = false;
      newForm = { id: '', name: '', description: '' };
      await loadList();
    } else if (r.status === 409) {
      showToast(r.data?.error || r.data?.detail || 'ID 已存在', 'error');
    } else {
      showToast(r.data?.error || r.data?.detail || '创建失败', 'error');
    }
  }

  // ---- 删除 ----
  async function removePersona() {
    if (!selected) return;
    const id = selected;
    const name = list.find((p) => p.id === id)?.name || '该角色';
    const ok = await confirmDialog(`确定删除「{name}」吗？此操作不可恢复。`, { title: '删除角色', danger: true });
    if (!ok) return;
    // 乐观删除：立即从本地列表移除，无需等待接口返回/返回上一步    list = list.filter((p) => p.id !== id);
    const r = await del(`/api/persona/${id}`);
    if (r.ok) {
      showToast('已删除', 'success');
      backToList();
      await loadList();
    } else {
      // 失败则回滚并提示
      await loadList();
      showToast(r.data?.error || r.data?.detail || (r.status === 409 ? '无法删除：存在关联数据' : '删除失败'), 'error');
    }
  }

  // ---- 头像 ----
  function onAvatarChange(e) {
    const file = e.target.files?.[0];
    if (!file || selected == null) return;
    uploadAvatar(file);
    e.target.value = '';
  }
  async function uploadAvatar(file) {
    const r = await postFile(`/api/persona/${selected}/avatar`, file, 'file');
    if (r.ok) {
      showToast('头像已更新', 'success');
      await loadDetail();
      await loadList();
    } else {
      showToast(r.data?.error || r.data?.detail || '头像上传失败', 'error');
    }
  }
  async function removeAvatar() {
    if (selected == null) return;
    const r = await del(`/api/persona/${selected}/avatar`);
    if (r.ok) {
      showToast('头像已移除', 'success');
      await loadDetail();
      await loadList();
    } else {
      showToast(r.data?.error || r.data?.detail || '移除头像失败', 'error');
    }
  }

  function goChat(id) {
    try {
      localStorage.setItem('cc-chat-persona', id);
    } catch {
      /* ignore */
    }
    goTab('chat');
  }

  let avatarInput = $state(null);
  let avatarSrc = $derived(detail?.avatar || list.find((p) => p.id === selected)?.avatar || '');
  let nameSlot = $derived(form['name'] || null);
</script>

<svelte:head><title>通讯录 · 慕</title></svelte:head>

<Toast {toast} />

<div class="page">
  {#if selected == null}
    <!-- ================= 列表视图 ================= -->
    <div class="page-top">
      <h1 class="page-title">通讯录</h1>
      <button class="btn btn-primary btn-sm" type="button" onclick={() => (showCreate = true)}>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建角色
      </button>
    </div>

    <div class="search-box">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="var(--text-3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        class="search-input"
        type="text"
        placeholder="搜索名字…"
        bind:value={query}
        aria-label="搜索角色"
      />
    </div>

    {#if loading}
      <div class="empty-state">
        <span class="empty-icon"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg></span>
        <p class="empty-desc">加载中…</p>
      </div>
    {:else if filtered.length === 0}
      <div class="empty-state">
        {#if list.length === 0}
          <span class="empty-icon"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>
          <p class="empty-title">还没有角色</p>
          <p class="empty-desc">点击右上角「新建角色」，创建你的第一位人设，一起开始聊天。</p>
          <button class="btn btn-primary empty-btn" type="button" onclick={() => (showCreate = true)}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            新建角色
          </button>
        {:else}
          <span class="empty-icon"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span>
          <p class="empty-title">没有匹配结果</p>
          <p class="empty-desc">换个关键词再试试。</p>
        {/if}
      </div>
    {:else}
      <ul class="list">
        {#each filtered as p, i (p.id)}
          <li class="card-row">
            <button class="row-main" type="button" onclick={() => openDetail(p.id)}>
              <Avatar name={p.name} src={p.avatar || ''} size={46} />
              <span class="row-name">{p.name}</span>
            </button>
            <button class="icon-btn outline" type="button" title="去聊天" onclick={() => goChat(p.id)}>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
            </button>
          </li>
        {/each}
      </ul>
    {/if}

  {:else}
    <!-- ================= 详情视图 ================= -->
    {#if detail == null}
      <div class="detail-head">
        <button class="icon-btn outline" type="button" onclick={backToList} aria-label="返回">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        </button>
        <span class="detail-title">{detailError || '加载中…'}</span>
        {#if detailError}
          <button class="btn btn-outline btn-sm" type="button" onclick={loadDetail}>重试</button>
        {/if}
      </div>
    {:else}
      <div class="detail-head">
        <button class="icon-btn outline" type="button" onclick={backToList} aria-label="返回">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        </button>
        <span class="detail-title">角色详情</span>
        <span class="detail-spacer"></span>
        <button class="btn btn-ghost btn-sm danger" type="button" onclick={removePersona}>删除</button>
      </div>

      <!-- 顶部固定区: 头像 + 名字 + 操作 -->
      <div class="hero-card card">
        <div class="hero-main">
          <div class="hero-avatar">
            <Avatar name={nameSlot?.value || ''} src={avatarSrc} size={84} />
            <button class="avatar-edit" type="button" title="更换头像" onclick={() => avatarInput?.click()} aria-label="更换头像">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            </button>
            <input
              bind:this={avatarInput}
              type="file"
              accept="image/*"
              style="display:none"
              onchange={onAvatarChange}
            />
          </div>
          <div class="hero-info">
            <input
              class="hero-name-input"
              type="text"
              placeholder="角色名字"
              value={nameSlot?.value || ''}
              oninput={(e) => {
                if (nameSlot) nameSlot.value = e.currentTarget.value;
              }}
              aria-label="角色名字"
            />
            <div class="avatar-actions">
              {#if avatarSrc}
                <button class="btn btn-ghost btn-sm" type="button" onclick={removeAvatar}>移除头像</button>
              {:else}
                <span class="hero-sub">在「基本信息」中保存后可更新头像</span>
              {/if}
            </div>
          </div>
        </div>
        <button class="btn btn-primary go-chat" type="button" onclick={() => goChat(selected)}>去聊天</button>
      </div>

      <!-- 精简人设卡 (PawzoChat 风格: 默认清爽视图 -->
      <div class="lean-section">
        {#each LEAN_CARDS as card (card.id)}
          <PersonaCard
            title={card.title}
            subtitle={card.subtitle}
            fields={card.fields}
            form={form}
            saving={saving}
            onsave={saveCard}
          />
        {/each}
      </div>

      <!-- 高级/全部字段折叠区: 普通字段 (默认收起) -->
      <PersonaAdvanced
        groups={ADVANCED_GROUPS}
        form={form}
        saving={saving}
        onsave={saveAdvanced}
      />

      <!-- 高级 Prompt 区 (友好、分层、不吓人) -->
      <PromptAdvancedPanel
        form={form}
        saving={saving}
        onsave={saveAdvanced}
      />
    {/if}
  {/if}
</div>

<!-- 新建弹窗 -->
{#if showCreate}
  <div class="overlay" role="dialog" aria-modal="true" aria-label="新建角色">
    <div class="modal card">
      <h2 class="modal-title">新建角色</h2>
      <label class="field">
        <span class="field-label">角色 ID</span>
        <input class="field-plain" type="text" placeholder="如 yue" bind:value={newForm.id} />
      </label>
      <label class="field">
        <span class="field-label">名字 *</span>
        <input class="field-plain" type="text" placeholder="如 小月" bind:value={newForm.name} />
      </label>
      <label class="field">
        <span class="field-label">描述</span>
        <textarea class="field-plain" rows="3" placeholder="可选的一句话介绍" bind:value={newForm.description}></textarea>
      </label>
      <div class="modal-actions">
        <button class="btn btn-outline" type="button" onclick={() => (showCreate = false)}>取消</button>
        <button class="btn btn-primary" type="button" disabled={creating} onclick={createPersona}>
          {creating ? '创建中…' : '创建'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page {
    padding: var(--space-5) var(--space-4) var(--space-7);
    max-width: 720px;
    margin: 0 auto;
  }

  /* ---- 列表区 ---- */
  .page-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }
  .page-title {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-1);
  }

  .search-box {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-4);
    height: var(--input-h);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    margin-bottom: var(--space-4);
  }
  .search-box:focus-within {
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .search-input {
    flex: 1;
    min-width: 0;
    border: none;
    background: transparent;
    color: var(--input-text);
    font-size: var(--text-base);
    outline: none;
  }
  .search-input::placeholder {
    color: var(--input-placeholder);
  }

  /* ---- 列表 ---- */
  .list {
    list-style: none;
    margin: 0;
    padding: var(--space-1);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    background: var(--surface);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--card-shadow);
  }
  .card-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--row-pad-y) var(--row-pad-x);
    border-radius: var(--row-radius);
    transition: background var(--transition);
  }
  .card-row:hover {
    background: var(--row-hover);
  }
  .card-row:active {
    background: var(--row-active);
  }
  .row-main {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    border: none;
    background: transparent;
    padding: 0;
    cursor: pointer;
    text-align: left;
    color: var(--text-1);
  }
  .row-name {
    font-size: var(--text-base);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ---- 详情区 ---- */
  .detail-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }
  .detail-title {
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-1);
  }
  .detail-spacer {
    flex: 1;
  }
  .btn.danger {
    color: var(--error);
  }
  .btn.danger:hover {
    background: color-mix(in srgb, var(--error) 12%, transparent);
  }

  /* ---- 顶部固定区 ---- */
  .hero-card {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
  }
  .hero-main {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }
  .hero-avatar {
    position: relative;
    flex: none;
  }
  .avatar-edit {
    position: absolute;
    right: -2px;
    bottom: -2px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-full);
    border: 2px solid var(--surface);
    background: var(--accent);
    color: var(--on-accent);
    cursor: pointer;
    transition: background var(--transition), transform var(--transition);
  }
  .avatar-edit:hover {
    background: var(--accent-strong);
  }
  .hero-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .hero-name-input {
    width: 100%;
    border: none;
    border-bottom: 1px solid transparent;
    background: transparent;
    color: var(--text-1);
    font-size: var(--text-xl);
    font-weight: 700;
    line-height: var(--leading-tight);
    padding: var(--space-1) 0;
    transition: border-color var(--transition);
  }
  .hero-name-input:focus-visible {
    outline: none;
    border-bottom-color: var(--input-focus-border);
  }
  .hero-name-input::placeholder {
    color: var(--input-placeholder);
    font-weight: 500;
  }
  .hero-sub {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .avatar-actions {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .go-chat {
    flex: none;
  }

  /* ---- 精简人设卡区 ---- */
  .lean-section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin-bottom: var(--space-2);
  }

  /* ---- 字段 ---- */
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .field-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
  }

  /* ---- 空状态 ---- */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: var(--space-3);
    min-height: 220px;
    padding: var(--space-7) var(--space-5);
    border: 1px dashed var(--border-strong);
    border-radius: var(--card-radius);
  }
  .empty-icon {
    display: inline-flex;
    color: var(--empty-icon);
  }
  .empty-title {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--empty-title);
  }
  .empty-desc {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--empty-text);
    max-width: 260px;
  }
  .empty-btn {
    margin-top: var(--space-1);
  }

  /* ---- 通用按钮 (对齐组件 token) ---- */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    border-radius: var(--btn-radius);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition), border-color var(--transition), transform var(--transition), box-shadow var(--transition);
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn-primary {
    height: var(--btn-h-md);
    padding: 0 var(--space-4);
    background: var(--btn-primary-bg);
    color: var(--btn-primary-text);
    box-shadow: var(--btn-primary-shadow);
  }
  .btn-primary:hover:not(:disabled) { background: var(--btn-primary-hover); }
  .btn-outline {
    height: var(--btn-h-md);
    padding: 0 var(--space-4);
    background: var(--btn-outline-bg);
    border-color: var(--btn-outline-border);
    color: var(--btn-outline-text);
  }
  .btn-outline:hover:not(:disabled) { background: var(--btn-outline-hover); }
  .btn-ghost {
    height: var(--btn-h-md);
    padding: 0 var(--space-3);
    background: transparent;
    color: var(--text-2);
  }
  .btn-ghost:hover:not(:disabled) { background: var(--row-hover); }
  .btn-sm { height: var(--btn-h-sm); padding: 0 var(--space-3); font-size: var(--text-xs); }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--btn-h-md);
    height: var(--btn-h-md);
    border-radius: var(--radius-full);
    border: 1px solid var(--btn-outline-border);
    background: var(--btn-outline-bg);
    color: var(--btn-outline-text);
    cursor: pointer;
    transition: background var(--transition), color var(--transition), transform var(--transition);
  }
  .icon-btn:hover { background: var(--btn-outline-hover); color: var(--accent); }
  .icon-btn:active { transform: scale(0.94); }

  /* ---- 弹窗 ---- */
  .overlay {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--overlay);
    padding: var(--space-4);
  }
  .modal {
    width: 100%;
    max-width: 420px;
    padding: var(--space-5);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    background: var(--surface);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--shadow-lg);
  }
  .modal-title {
    margin: 0 0 var(--space-1);
    font-size: var(--text-lg);
    font-weight: 700;
    color: var(--text-1);
  }
  .field-plain {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    color: var(--input-text);
    font-size: var(--text-base);
    line-height: var(--leading-snug);
  }
  .field-plain:focus-visible {
    outline: none;
    border-color: var(--input-focus-border);
    box-shadow: var(--focus-ring);
  }
  .field-plain::placeholder {
    color: var(--input-placeholder);
  }
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  /* 桌面区: 卡片更舒适*/
  @media (min-width: 768px) {
    .hero-card {
      padding: var(--space-5);
    }
  }
</style>
