<script>
  // ============================================================
  // MemoryPage.svelte — 记忆: 重要记忆 + 大脑日记
  //
  // 重要记忆:
  //   GET /api/memory?conversation_id=&persona_id=&offset=&limit=&level_min=&level_max=
  //     -> { messages:[...], total:N }   (key WEN messages)
  //   每条 {id,content,level,category,created_at,tags,source,confidence,last_accessed}
  //   详情 GET /api/memory/{id}?conversation_id=&persona_id= -> 含 access_count,
  //        related_memory_ids,superseded_by,forget_score,archived
  //   删除 DELETE /api/memory/{id}?conversation_id=&persona_id=
  //
  // 大脑日记:
  //   GET /api/life_summary?persona_id=&conversation_id=&limit=20 -> {summaries,total}
  //   每条 {id,summary_type,summary,recent_status,key_events,message_count,created_at,emotional_trends}
  //   GET /api/life_summary/latest -> 可能返回 null
  // ============================================================
import { get, del } from '../lib/pages-api.js';
import { friendlyTime } from '../lib/format.js';
import { confirmDialog } from '../lib/dialog.svelte.js';
import Toast from '../components/Toast.svelte';

  const LIMIT = 20;

  let tab = $state('memory'); // 'memory' | 'diary'

  // ---- 重要记忆 ----
  let messages = $state([]);
  let total = $state(0);
  let offset = $state(0);
  let loading = $state(true);
  let loadingMore = $state(false);
  let openId = $state(null);
  let detailMap = $state({}); // id -> detail dict
  let loadingDetailId = $state(null);

  // ---- 大脑日记 ----
  let summaries = $state([]);
  let summaryTotal = $state(0);
  let diaryLoading = $state(true);
  let diaryLoadingMore = $state(false);
  let summaryOffset = $state(0);
  let latest = $state(null); // 最新摘要(可为 null)
  let latestLoading = $state(true);

  let toast = $state(null);
  let toastTimer = null;

  function qs(extra = {}) {
    const p = new URLSearchParams();
    // 契约要求这些参数以空值出现
    p.set('conversation_id', '');
    p.set('persona_id', '');
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null && v !== '') p.set(k, v);
    }
    return p.toString();
  }

  function showToast(text, type = 'info') {
    toast = { text, type };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2400);
  }

  async function loadMemory(reset = true) {
    if (reset) {
      loading = true;
      messages = [];
      offset = 0;
      total = 0;
      openId = null;
      detailMap = {};
      const r = await get(`/api/memory?${qs({ offset: 0, limit: LIMIT, level_min: 1, level_max: 5 })}`);
      loading = false;
      if (r.ok) {
        messages = r.data.messages || [];
        total = r.data.total ?? messages.length;
        offset = messages.length;
      } else {
        showToast(r.data?.error || r.data?.detail || '加载记忆失败', 'error');
      }
    } else {
      loadingMore = true;
      const r = await get(`/api/memory?${qs({ offset, limit: LIMIT, level_min: 1, level_max: 5 })}`);
      loadingMore = false;
      if (r.ok) {
        messages = [...messages, ...(r.data.messages || [])];
        total = r.data.total ?? messages.length;
        offset = messages.length;
      } else {
        showToast(r.data?.error || '加载更多失败', 'error');
      }
    }
  }

  async function toggleDetail(m) {
    if (openId === m.id) {
      openId = null;
      return;
    }
    openId = m.id;
    if (detailMap[m.id]) return;
    loadingDetailId = m.id;
    const r = await get(`/api/memory/${m.id}?${qs()}`);
    loadingDetailId = null;
    if (r.ok && r.data) {
      detailMap[m.id] = r.data;
    } else {
      showToast(r.data?.error || r.data?.detail || '加载详情失败', 'error');
    }
  }

  async function removeMemory(m) {
    const ok = await confirmDialog('确定删除这条记忆吗？此操作不可恢复。', { title: '删除记忆', danger: true });
    if (!ok) return;
    const r = await del(`/api/memory/${m.id}?${qs()}`);
    if (r.ok) {
      showToast('记忆已删除', 'success');
      if (openId === m.id) openId = null;
      messages = messages.filter((x) => x.id !== m.id);
      total = Math.max(0, total - 1);
    } else {
      showToast(r.data?.error || r.data?.detail || '删除失败', 'error');
    }
  }

  // ---- 大脑日记 ----
  async function loadDiary(reset = true) {
    const loadLatest = async () => {
      latestLoading = true;
      const r = await get('/api/life_summary/latest');
      latestLoading = false;
      if (r.ok) latest = r.data || null;
      else latest = null;
    };
    if (reset) {
      diaryLoading = true;
      summaries = [];
      summaryOffset = 0;
      summaryTotal = 0;
      const [r] = await Promise.all([get(`/api/life_summary?${qs({ limit: LIMIT })}`), loadLatest()]);
      diaryLoading = false;
      if (r.ok) {
        summaries = r.data.summaries || [];
        summaryTotal = r.data.total ?? summaries.length;
        summaryOffset = summaries.length;
      } else {
        showToast(r.data?.error || r.data?.detail || '加载日记失败', 'error');
      }
    } else {
      diaryLoadingMore = true;
      const r = await get(`/api/life_summary?${qs({ limit: LIMIT, offset: summaryOffset })}`);
      diaryLoadingMore = false;
      if (r.ok) {
        summaries = [...summaries, ...(r.data.summaries || [])];
        summaryTotal = r.data.total ?? summaries.length;
        summaryOffset = summaries.length;
      } else {
        showToast(r.data?.error || '加载更多失败', 'error');
      }
    }
  }

  function levelColor(lv) {
    // 重要度 1-5 -> 语义色
    if (lv >= 5) return 'var(--error)';
    if (lv >= 4) return 'var(--warning)';
    if (lv >= 3) return 'var(--accent)';
    if (lv >= 2) return 'var(--info)';
    return 'var(--text-3)';
  }

  $effect(() => {
    if (tab === 'memory') loadMemory(true);
    else loadDiary(true);
  });
</script>

<svelte:head><title>记忆 · 慕</title></svelte:head>

<Toast {toast} />

<div class="page">
  <h1 class="page-title">记忆</h1>

  <div class="tabs" role="tablist">
    <button class="tab-btn {tab === 'memory' ? 'is-active' : ''}" role="tab" type="button" onclick={() => (tab = 'memory')}>重要记忆</button>
    <button class="tab-btn {tab === 'diary' ? 'is-active' : ''}" role="tab" type="button" onclick={() => (tab = 'diary')}>大脑日记</button>
  </div>

  {#if tab === 'memory'}
    <!-- ============ 重要记忆 ============ -->
    {#if loading}
      <div class="empty-state"><p class="empty-desc">加载中…</p></div>
    {:else if messages.length === 0}
      <div class="empty-state">
        <p class="empty-title">还没有重要记忆</p>
        <p class="empty-desc">与角色深入交流后，重要的内容会沉淀到这里。</p>
      </div>
    {:else}
      <div class="list">
        {#each messages as m (m.id)}
          <div class="mem-item">
            <button class="mem-main" type="button" onclick={() => toggleDetail(m)}>
              <div class="mem-head">
                <span class="mem-level" style="background:{levelColor(m.level)}" title="重要度 {m.level}"></span>
                <span class="mem-category">{m.category || '未分类'}</span>
                <span class="mem-time">{friendlyTime(m.created_at)}</span>
                {#if m.source}<span class="mem-source">{m.source}</span>{/if}
              </div>
              <p class="mem-content">{m.content}</p>
              <div class="mem-tags">
                <span class="mem-meta">重要度 {m.level}</span>
                {#if m.confidence != null}<span class="mem-meta">置信度 {m.confidence}</span>{/if}
                {#each (m.tags || []).slice(0, 5) as t (t)}
                  <span class="tag">#{t}</span>
                {/each}
              </div>
            </button>

            {#if openId === m.id}
              <div class="mem-detail">
                {#if loadingDetailId === m.id}
                  <p class="empty-desc">加载详情…</p>
                {:else if detailMap[m.id]}
                  {@const d = detailMap[m.id]}
                  {#if d.access_count != null}
                    <div class="detail-row"><span class="detail-k">访问次数</span><span class="detail-v">{d.access_count}</span></div>
                  {/if}
                  {#if d.forget_score != null}
                    <div class="detail-row"><span class="detail-k">遗忘指数</span><span class="detail-v">{d.forget_score}</span></div>
                  {/if}
                  {#if d.archived != null}
                    <div class="detail-row"><span class="detail-k">已归档</span><span class="detail-v">{d.archived ? '是' : '否'}</span></div>
                  {/if}
                  {#if d.superseded_by}
                    <div class="detail-row"><span class="detail-k">已被取代</span><span class="detail-v">{typeof d.superseded_by === 'object' ? JSON.stringify(d.superseded_by) : d.superseded_by}</span></div>
                  {/if}
                  {#if (d.related_memory_ids || []).length > 0}
                    <div class="detail-row"><span class="detail-k">关联记忆</span><span class="detail-v">{(d.related_memory_ids || []).join(', ')}</span></div>
                  {/if}
                  {#if d.last_accessed}
                    <div class="detail-row"><span class="detail-k">上次访问</span><span class="detail-v">{friendlyTime(d.last_accessed)}</span></div>
                  {/if}
                {/if}
                <button class="btn btn-outline btn-sm del-btn" type="button" onclick={() => removeMemory(m)}>删除此记忆</button>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      {#if offset < total}
        <div class="load-more">
          <button class="btn btn-outline" type="button" disabled={loadingMore} onclick={() => loadMemory(false)}>
            {loadingMore ? '加载中…' : `加载更多 (${offset}/${total})`}
          </button>
        </div>
      {/if}
    {/if}

  {:else}
    <!-- ============ 大脑日记 ============ -->
    {#if latest}
      <div class="latest card">
        <div class="latest-head">
          <span class="latest-badge">最新摘要</span>
          <span class="latest-time">{friendlyTime(latest.created_at)}</span>
        </div>
        <p class="latest-summary">{latest.summary}</p>
        {#if (latest.key_events || []).length > 0}
          <div class="tags-row">
            {#each (latest.key_events || []).slice(0, 8) as e (e)}
              <span class="tag">{e}</span>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    {#if diaryLoading}
      <div class="empty-state"><p class="empty-desc">加载中…</p></div>
    {:else if summaries.length === 0}
      <div class="empty-state">
        <p class="empty-title">还没有大脑日记</p>
        <p class="empty-desc">记忆会按周期整理成总结日记。</p>
      </div>
    {:else}
      <div class="diary-list">
        {#each summaries as s (s.id)}
          <article class="diary card">
            <header class="diary-head">
              <span class="diary-type">{s.summary_type || '总结'}</span>
              <span class="diary-time">{friendlyTime(s.created_at)}</span>
            </header>
            <p class="diary-summary">{s.summary}</p>

            {#if (s.key_events || []).length > 0}
              <div class="block">
                <span class="block-label">关键事件</span>
                <div class="tags-row">
                  {#each (s.key_events || []) as e (e)}
                    <span class="tag">{e}</span>
                  {/each}
                </div>
              </div>
            {/if}

            {#if s.recent_status || s.emotional_trends}
              <div class="block">
                {#if s.recent_status}
                  <div class="kv"><span class="kv-k">近期状态</span><span class="kv-v">{s.recent_status}</span></div>
                {/if}
                {#if s.emotional_trends}
                  <div class="kv"><span class="kv-k">情绪趋势</span><span class="kv-v">{typeof s.emotional_trends === 'object' ? JSON.stringify(s.emotional_trends) : s.emotional_trends}</span></div>
                {/if}
              </div>
            {/if}

            {#if s.message_count != null}
              <footer class="diary-foot">共 {s.message_count} 条消息</footer>
            {/if}
          </article>
        {/each}
      </div>

      {#if summaryOffset < summaryTotal}
        <div class="load-more">
          <button class="btn btn-outline" type="button" disabled={diaryLoadingMore} onclick={() => loadDiary(false)}>
            {diaryLoadingMore ? '加载中…' : `加载更多 (${summaryOffset}/${summaryTotal})`}
          </button>
        </div>
      {/if}
    {/if}
  {/if}
</div>

<style>
  .page {
    padding: var(--space-5) var(--space-4) var(--space-7);
    max-width: 720px;
    margin: 0 auto;
  }
  .page-title {
    margin: 0 0 var(--space-4);
    font-size: var(--text-xl);
    font-weight: 700;
    color: var(--text-1);
  }

  .tabs {
    display: flex;
    gap: var(--space-1);
    margin-bottom: var(--space-4);
    padding: var(--space-1);
    background: var(--surface-2);
    border-radius: var(--radius);
  }
  .tab-btn {
    flex: 1;
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .tab-btn:hover { color: var(--text-1); }
  .tab-btn.is-active {
    background: var(--surface);
    color: var(--accent);
    box-shadow: var(--shadow-sm);
  }

  /* ---- 重要记忆 ---- */
  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .mem-item {
    background: var(--surface);
    border: 1px solid var(--card-border);
    border-radius: var(--card-radius);
    box-shadow: var(--card-shadow);
    overflow: hidden;
  }
  .mem-main {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-4);
    border: none;
    background: transparent;
    text-align: left;
    cursor: pointer;
    color: var(--text-1);
  }
  .mem-main:hover { background: var(--row-hover); }
  .mem-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .mem-level {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    flex: none;
  }
  .mem-category {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--accent);
    background: var(--tint);
    padding: 1px var(--space-2);
    border-radius: var(--radius-full);
  }
  .mem-time {
    font-size: var(--text-xs);
    color: var(--text-3);
    margin-left: auto;
  }
  .mem-source {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .mem-content {
    margin: 0;
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--text-1);
  }
  .mem-tags {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .mem-meta {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .tag {
    font-size: var(--text-xs);
    color: var(--info);
    background: color-mix(in srgb, var(--info) 12%, transparent);
    padding: 1px var(--space-2);
    border-radius: var(--radius-full);
  }
  .mem-detail {
    padding: var(--space-3) var(--space-4) var(--space-4);
    border-top: 1px solid var(--border);
    background: var(--surface-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .detail-row {
    display: flex;
    gap: var(--space-3);
    font-size: var(--text-sm);
  }
  .detail-k {
    flex: none;
    width: 72px;
    color: var(--text-3);
  }
  .detail-v {
    color: var(--text-1);
    word-break: break-word;
  }
  .del-btn {
    align-self: flex-end;
    color: var(--error);
    border-color: var(--error);
    margin-top: var(--space-1);
  }

  /* ---- 大脑日记 ---- */
  .latest {
    padding: var(--space-4);
    margin-bottom: var(--space-4);
    border-left: 3px solid var(--accent);
  }
  .latest-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .latest-badge {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--accent-contrast);
    background: var(--accent);
    padding: 2px var(--space-2);
    border-radius: var(--radius-full);
  }
  .latest-time { font-size: var(--text-xs); color: var(--text-3); }
  .latest-summary {
    margin: 0;
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--text-1);
  }

  .diary-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .diary {
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .diary-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .diary-type {
    font-size: var(--text-xs);
    font-weight: 700;
    color: var(--accent-contrast);
    background: var(--accent);
    padding: 2px var(--space-2);
    border-radius: var(--radius-full);
    text-transform: uppercase;
  }
  .diary-time {
    font-size: var(--text-xs);
    color: var(--text-3);
    margin-left: auto;
  }
  .diary-summary {
    margin: 0;
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--text-1);
  }
  .block {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--surface-2);
    border-radius: var(--radius);
  }
  .block-label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--text-2);
  }
  .tags-row { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .kv { display: flex; gap: var(--space-3); font-size: var(--text-sm); }
  .kv-k { flex: none; color: var(--text-3); }
  .kv-v { color: var(--text-1); word-break: break-word; }
  .diary-foot {
    font-size: var(--text-xs);
    color: var(--text-3);
    border-top: 1px solid var(--border);
    padding-top: var(--space-2);
  }

  .load-more {
    display: flex;
    justify-content: center;
    margin-top: var(--space-5);
  }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
    border-radius: var(--btn-radius); font-size: var(--text-sm); font-weight: 600;
    cursor: pointer; border: 1px solid transparent; white-space: nowrap;
    transition: background var(--transition), border-color var(--transition), transform var(--transition), box-shadow var(--transition);
  }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn-outline {
    height: var(--btn-h-md); padding: 0 var(--space-4);
    background: var(--btn-outline-bg); border-color: var(--btn-outline-border); color: var(--btn-outline-text);
  }
  .btn-outline:hover:not(:disabled) { background: var(--btn-outline-hover); }
  .btn-sm { height: var(--btn-h-sm); padding: 0 var(--space-3); font-size: var(--text-xs); }

  .empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
    gap: var(--space-2); min-height: 200px; padding: var(--space-7) var(--space-5);
    border: 1px dashed var(--border-strong); border-radius: var(--card-radius);
  }
  .empty-title { margin: 0; font-size: var(--text-lg); font-weight: 600; color: var(--empty-title); }
  .empty-desc { margin: 0; font-size: var(--text-sm); color: var(--empty-text); }
</style>
