/* ===== voice-bubble.js — 网页端可播放语音气泡（PawzoChat 微信风格）=====
 *
 * 把后端合成的语音（/api/audio/... 或任意 URL）渲染成可点击播放的气泡：
 * - ▶ 播放 / ⏸ 暂停
 * - 波纹动画（播放时激活）
 * - 时长显示（加载完成后显示秒数）
 * 渲染安全：全部用 textContent / createElement，不拼 HTML。
 */

import { el } from "./state.js";

const BAR_COUNT = 14;

/**
 * 在容器里追加一个语音气泡，点击播放/暂停。返回气泡元素。
 * @param {HTMLElement} container 容器（通常是 .bubble）
 * @param {string} url 音频 URL
 */
export function appendVoiceBubble(container, url) {
  const bubble = el("div", "voice-bubble");
  bubble.dataset.playing = "0";

  const playBtn = el("div", "voice-play");
  playBtn.textContent = "▶";

  const waves = el("div", "voice-waves");
  for (let i = 0; i < BAR_COUNT; i += 1) {
    const bar = document.createElement("span");
    bar.style.setProperty("--i", i);
    waves.appendChild(bar);
  }

  const dur = el("span", "voice-dur");
  dur.textContent = "…";

  bubble.appendChild(playBtn);
  bubble.appendChild(waves);
  bubble.appendChild(dur);

  const audio = document.createElement("audio");
  audio.src = url;
  audio.preload = "metadata";
  audio.hidden = true;
  bubble.appendChild(audio);

  let timer = null;

  function setPlaying(on) {
    bubble.dataset.playing = on ? "1" : "0";
    playBtn.textContent = on ? "⏸" : "▶";
    if (on) {
      if (timer) clearInterval(timer);
      timer = setInterval(() => {
        if (!Number.isFinite(audio.currentTime)) return;
        dur.textContent = Math.ceil(audio.currentTime) + "″";
      }, 500);
    } else if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  audio.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(audio.duration)) {
      dur.textContent = Math.ceil(audio.duration) + "″";
    }
  });
  audio.addEventListener("ended", () => { setPlaying(false); });
  audio.addEventListener("error", () => {
    dur.textContent = "无法播放";
    bubble.classList.add("voice-error");
    setPlaying(false);
  });

  bubble.addEventListener("click", () => {
    if (bubble.dataset.playing === "1") {
      audio.pause();
      setPlaying(false);
    } else {
      audio.play().then(() => setPlaying(true)).catch(() => {
        dur.textContent = "无法播放";
      });
    }
  });

  container.appendChild(bubble);
  return bubble;
}
