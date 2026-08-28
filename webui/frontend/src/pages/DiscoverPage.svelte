<script>
  // ============================================================
  // DiscoverPage.svelte — 发现 / 朋友圈  //
  // - GET /api/moments?limit=&offset= -> {moments:[...], has_more}
  // - 点赞  POST/DELETE /api/moments/{id}/like
  // - 评论  POST /api/moments/{id}/replies {text, reply_to?}
  // - 删除动态 DELETE /api/moments/{id}
  // - 删除评论 DELETE /api/moments/{id}/replies/{reply_id}
  // - 发布  POST /api/moments {text, author?} (作者下拉获取 GET /api/moments/personas)
  // - 加载更多 offset 用 limit 累加
  // ============================================================
import { get, post, del } from '../lib/pages-api.js';
import { friendlyTime } from '../lib/format.js';
import { confirmDialog } from '../lib/dialog.svelte.js';
import Avatar from '../components/Avatar.svelte';
import Toast from '../components/Toast.svelte';

  const LIMIT = 20;

  let moments = $state([]);
  let hasMore = $state(false);
  let offset = $state(0);
  let loading = $state(true);
  let loadingMore = $state(false);
  let toast = $state(null);
  let toastTimer = null;

  // 发布
  let publishOpen = $state(false);
  let newText = $state('');
  let newAuthor = $state('');
  let personas = $state([]);
  let publishing = $state(false);
  let authorLoading = $state(false);

  // 评论
  let openReplyId = $state(null);
  let replyDrafts = $state({}); // momentId -> text
  let replyTarget = $state(null); // {momentId, reply_id?, reply_to_label?}

  // 点赞本地覆盖: id -> bool
  let likedOverride = $state({});

  async function loadInitial() {
    loading = true;
    const r = await get(`/api/moments?limit=${LIMIT}&offset=0`);
    loading = false;
    if (r.ok) {
      moments = r.data.moments || [];
      offset = moments.length;
      hasMore = !!r.data.has_more;
    } else {
      moments = [];
      hasMore = false;
      showToast(r.data?.error || r.data?.detail || '加载失败', 'error');
    }
  }

  $effect(() => {
    loadInitial();
    loadPersonas();
  });

  async function loadPersonas() {
    authorLoading = true;
    const r = await get('/api/moments/personas');
    authorLoading = false;
    if (r.ok && Array.isArray(r.data?.personas)) personas = r.data.personas;
  }

  function showToast(text, type = 'info') {
    toast = { text, type };
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2400);
  }

  // 轻量刷新: 拉取与当前相同数量的最新条目 (用于发布/评论后)
  async function reload(keepCount = moments.length) {
    const count = Math.max(keepCount, LIMIT);
    const r = await get(`/api/moments?limit=${count}&offset=0`);
    if (r.ok) {
      moments = r.data.moments || [];
      offset = moments.length;
      hasMore = !!r.data.has_more;
    }
  }

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    loadingMore = true;
    const r = await get(`/api/moments?limit=${LIMIT}&offset=${offset}`);
    loadingMore = false;
    if (r.ok) {
      moments = [...moments, ...(r.data.moments || [])];
      offset = moments.length;
      hasMore = !!r.data.has_more;
    } else {
      showToast(r.data?.error || '加载更多失败', 'error');
    }
  }

  // ---- 点赞 ----
  function likedByMe(m) {
    if (likedOverride[m.id] !== undefined) return likedOverride[m.id];
    return m.liked_by_me === true || m.liked === true;
  }
  async function toggleLike(m) {
    const active = likedByMe(m);
    const r = active ? await del(`/api/moments/${m.id}/like`) : await post(`/api/moments/${m.id}/like`, {});
    if (!r.ok) {
      showToast(r.data?.error || r.data?.detail || (active ? '取消点赞失败' : '点赞失败'), 'error');
      return;
    }
    likedOverride[m.id] = !active;
    // 同步 likes 数组
    if (!active) {
      if (!Array.isArray(m.likes)) m.likes = [];
      m.likes = [...m.likes, { author: 'me', author_label: '我' }];
    } else {
      m.likes = (m.likes || []).filter((l) => l.author !== 'me' && l.author_label !== '我');
    }
  }

  // ---- 评论 ----
  function toggleReply(m) {
    if (openReplyId === m.id) {
      openReplyId = null;
      replyTarget = null;
    } else {
      openReplyId = m.id;
      replyTarget = null;
      if (replyDrafts[m.id] === undefined) replyDrafts[m.id] = '';
    }
  }
  function openReplyTo(m, rp) {
    openReplyId = m.id;
    if (replyDrafts[m.id] === undefined) replyDrafts[m.id] = '';
    replyTarget = { momentId: m.id, replyId: rp.id, replyToLabel: rp.author_label || rp.author };
  }
  function cancelReplyTo(m) {
    replyTarget = null;
  }
  async function submitReply(m) {
    const text = (replyDrafts[m.id] || '').trim();
    if (!text) return;
    const body = { text };
    if (replyTarget?.momentId === m.id && replyTarget.replyId) body.reply_to = replyTarget.replyId;
    const r = await post(`/api/moments/${m.id}/replies`, body);
    if (!r.ok) {
      showToast(r.data?.error || r.data?.detail || '评论失败', 'error');
      return;
    }
    replyDrafts[m.id] = '';
    replyTarget = null;
    openReplyId = null;
    showToast('评论已发布', 'success');
    await reload();
  }

  // ---- 删除 ----
  async function removeMoment(m) {
    const label = m.author_label || m.author || '该动态';
    const ok = await confirmDialog(`确定删除 ${label} 的这条动态吗？`, { title: '删除动态', danger: true });
    if (!ok) return;
    const r = await del(`/api/moments/${m.id}`);
    if (r.ok) {
      showToast('动态已删除', 'success');
      await reload();
    } else {
      showToast(r.data?.error || r.data?.detail || '删除失败', 'error');
    }
  }
  async function removeReply(m, rp) {
    const ok = await confirmDialog('确定删除这条评论吗？', { title: '删除评论', danger: true });
    if (!ok) return;
    const r = await del(`/api/moments/${m.id}/replies/${rp.id}`);
    if (r.ok) {
      showToast('评论已删除', 'success');
      await reload();
    } else {
      showToast(r.data?.error || r.data?.detail || '删除失败', 'error');
    }
  }

  // ---- 发布 ----
  function openPublish() {
    publishOpen = !publishOpen;
  }
  async function submitPublish() {
    const text = newText.trim();
    if (!text) return;
    publishing = true;
    const body = { text };
    if (newAuthor) body.author = newAuthor;
    const r = await post('/api/moments', body);
    publishing = false;
    if (r.ok) {
      showToast('已发布', 'success');
      newText = '';
      newAuthor = '';
      publishOpen = false;
      await reload();
    } else {
      showToast(r.data?.error || r.data?.detail || '发布失败', 'error');
    }
  }
</script>

<svelte:head><title>发现 · 慕</title></svelte:head>

<Toast {toast} />

<div class="page">
  <div class="page-top">
    <h1 class="page-title">发现</h1>
    <button class="btn btn-primary btn-sm" type="button" onclick={openPublish}>＋发布</button>
  </div>

  <!-- 发布框 -->
  {#if publishOpen}
    <div class="publish card">
      <label class="field">
        <span class="field-label">正文</span>
        <textarea class="field-input" rows="4" placeholder="分享此刻…" bind:value={newText}></textarea>
      </label>
      <label class="field">
        <span class="field-label">作者：{authorLoading ? '(加载中…' : ''}</span>
        <select class="field-input" bind:value={newAuthor}>
          <option value="">以我本人发布</option>
          {#each personas as p (p.id)}
            <option value={p.id}>{p.name}</option>
          {/each}
        </select>
      </label>
      <div class="form-actions">
        <button class="btn btn-outline btn-sm" type="button" onclick={() => (publishOpen = false)}>取消</button>
        <button class="btn btn-primary btn-sm" type="button" disabled={publishing || !newText.trim()} onclick={submitPublish}>
          {publishing ? '发布中…' : '发布'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="empty-state"><p class="empty-desc">加载中…</p></div>
  {:else if moments.length === 0}
    <div class="empty-state">
      <p class="empty-title">还没有动态</p>
      <p class="empty-desc">点右上角「发布」记录此刻的想法。</p>
    </div>
  {:else}
    <div class="timeline">
      {#each moments as m (m.id)}
        <article class="moment card">
          <header class="moment-head">
            <Avatar name={m.author_label || m.author || '?'} src={m.author_avatar || ''} size={42} />
            <div class="moment-meta">
              <span class="moment-author">{m.author_label || m.author || '匿名'}</span>
              <span class="moment-time">{friendlyTime(m.timestamp)}</span>
            </div>
            <button class="icon-btn ghost" type="button" title="删除动态" onclick={() => removeMoment(m)}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </header>

          <p class="moment-text">{m.text}</p>

          {#if (m.likes || []).length > 0}
            <div class="likes-row">
              <span class="likes-icon" aria-hidden="true">♥</span>
              <span class="likes-text">
                {(m.likes || []).map((l) => l.author_label || l.author).join('、')}
              </span>
            </div>
          {/if}

          <footer class="moment-foot">
            <button class="foot-btn {likedByMe(m) ? 'is-liked' : ''}" type="button" onclick={() => toggleLike(m)}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="{likedByMe(m) ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>
              {likedByMe(m) ? '已赞' : '赞'}
            </button>
            <button class="foot-btn" type="button" onclick={() => toggleReply(m)}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
              评论
            </button>
          </footer>

          {#if (m.replies || []).length > 0}
            <div class="replies">
              {#each m.replies as rp (rp.id)}
                <div class="reply">
                  <span class="reply-author">{rp.author_label || rp.author || '匿名'}</span>
                  {#if rp.reply_to_label || rp.reply_to}
                    <span class="reply-arrow">回复</span>
                    <span class="reply-to">{rp.reply_to_label || rp.reply_to}</span>
                  {/if}
                  <span class="reply-colon">：</span>
                  <span class="reply-text">{rp.text}</span>
                  <div class="reply-actions">
                    <button class="mini-btn" type="button" onclick={() => openReplyTo(m, rp)}>回复</button>
                    <button class="mini-btn danger" type="button" onclick={() => removeReply(m, rp)}>删除</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          {#if openReplyId === m.id}
            <div class="reply-box">
              {#if replyTarget?.momentId === m.id && replyTarget.replyToLabel}
                <div class="reply-target">
                  回复 @{replyTarget.replyToLabel}
                  <button class="mini-btn" type="button" onclick={cancelReplyTo}>取消</button>
                </div>
              {/if}
              <div class="reply-input-row">
                <input
                  class="field-input"
                  type="text"
                  placeholder="写评论…"
                  bind:value={replyDrafts[m.id]}
                  onkeydown={(e) => { if (e.key === 'Enter') submitReply(m); }}
                />
                <button class="btn btn-primary btn-sm" type="button" disabled={!(replyDrafts[m.id] || '').trim()} onclick={() => submitReply(m)}>发送</button>
              </div>
            </div>
          {/if}
        </article>
      {/each}
    </div>

    {#if hasMore}
      <div class="load-more">
        <button class="btn btn-outline" type="button" disabled={loadingMore} onclick={loadMore}>
          {loadingMore ? '加载中…' : '加载更多'}
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .page {
    padding: var(--space-5) var(--space-4) var(--space-7);
    max-width: 720px;
    margin: 0 auto;
  }
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

  /* 发布框 */
  .publish {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .timeline {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .moment {
    padding: var(--space-4);
  }
  .moment-head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .moment-meta {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .moment-author {
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--text-1);
  }
  .moment-time {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .moment-text {
    margin: var(--space-3) 0;
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--text-1);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .likes-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    margin-bottom: var(--space-2);
    background: var(--surface-2);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .likes-icon {
    color: var(--error);
  }
  .likes-text {
    flex: 1;
    min-width: 0;
  }

  .moment-foot {
    display: flex;
    gap: var(--space-2);
    border-top: 1px solid var(--border);
    padding-top: var(--space-2);
  }
  .foot-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-3);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-2);
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
  }
  .foot-btn:hover {
    background: var(--row-hover);
    color: var(--text-1);
  }
  .foot-btn.is-liked {
    color: var(--error);
  }

  .replies {
    margin-top: var(--space-2);
    padding: var(--space-3);
    background: var(--surface-2);
    border-radius: var(--radius);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .reply {
    display: flex;
    align-items: baseline;
    gap: var(--space-1);
    font-size: var(--text-sm);
    line-height: var(--leading-snug);
    flex-wrap: wrap;
  }
  .reply-author {
    font-weight: 600;
    color: var(--info);
  }
  .reply-arrow {
    color: var(--text-3);
    font-size: var(--text-xs);
  }
  .reply-to {
    font-weight: 600;
    color: var(--info);
  }
  .reply-colon {
    color: var(--text-2);
  }
  .reply-text {
    color: var(--text-1);
    min-width: 0;
    flex: 1;
  }
  .reply-actions {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
  }

  .mini-btn {
    border: none;
    background: transparent;
    color: var(--text-3);
    font-size: var(--text-xs);
    cursor: pointer;
    padding: 0;
    transition: color var(--transition);
  }
  .mini-btn:hover { color: var(--info); }
  .mini-btn.danger:hover { color: var(--error); }

  .reply-box {
    margin-top: var(--space-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .reply-target {
    font-size: var(--text-xs);
    color: var(--text-2);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .reply-input-row {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .reply-input-row .field-input {
    flex: 1;
    border-radius: var(--input-radius);
  }

  .load-more {
    display: flex;
    justify-content: center;
    margin-top: var(--space-5);
  }

  /* ---- 表单/按钮通用 ---- */
  .field { display: flex; flex-direction: column; gap: var(--space-2); }
  .field-label { font-size: var(--text-sm); font-weight: 600; color: var(--text-2); }
  .field-input {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: var(--input-bg);
    border: 1px solid var(--input-border);
    border-radius: var(--input-radius);
    color: var(--input-text);
    font-size: var(--text-base);
    font-family: var(--font-sans);
    line-height: var(--leading-snug);
  }
  .field-input:focus-visible { outline: none; border-color: var(--input-focus-border); box-shadow: var(--focus-ring); }
  .field-input::placeholder { color: var(--input-placeholder); }
  .form-actions { display: flex; justify-content: flex-end; gap: var(--space-2); }

  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
    border-radius: var(--btn-radius); font-size: var(--text-sm); font-weight: 600;
    cursor: pointer; border: 1px solid transparent; white-space: nowrap;
    transition: background var(--transition), border-color var(--transition), transform var(--transition), box-shadow var(--transition);
  }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn-primary {
    height: var(--btn-h-md); padding: 0 var(--space-4);
    background: var(--btn-primary-bg); color: var(--btn-primary-text); box-shadow: var(--btn-primary-shadow);
  }
  .btn-primary:hover:not(:disabled) { background: var(--btn-primary-hover); }
  .btn-outline {
    height: var(--btn-h-md); padding: 0 var(--space-4);
    background: var(--btn-outline-bg); border-color: var(--btn-outline-border); color: var(--btn-outline-text);
  }
  .btn-outline:hover:not(:disabled) { background: var(--btn-outline-hover); }
  .btn-sm { height: var(--btn-h-sm); padding: 0 var(--space-3); font-size: var(--text-xs); }

  .icon-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: var(--btn-h-md); height: var(--btn-h-md); border-radius: var(--radius-full);
    border: 1px solid var(--btn-outline-border); background: var(--btn-outline-bg); color: var(--btn-outline-text);
    cursor: pointer; transition: background var(--transition), color var(--transition), transform var(--transition);
  }
  .icon-btn:hover { background: var(--btn-outline-hover); color: var(--error); }
  .icon-btn.ghost { border-color: transparent; color: var(--text-3); }
  .icon-btn:active { transform: scale(0.94); }

  .empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
    gap: var(--space-2); min-height: 220px; padding: var(--space-7) var(--space-5);
    border: 1px dashed var(--border-strong); border-radius: var(--card-radius);
  }
  .empty-title { margin: 0; font-size: var(--text-lg); font-weight: 600; color: var(--empty-title); }
  .empty-desc { margin: 0; font-size: var(--text-sm); color: var(--empty-text); }
</style>
