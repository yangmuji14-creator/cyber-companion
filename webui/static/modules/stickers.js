import { state, dom } from "./state.js";
import { toast } from "./ui.js";
import { sendMessage } from "./chat-stream.js?v=4.3.11";

let groups = [];

export async function loadStickers() {
  try {
    const response = await fetch("/api/stickers", { cache: "no-store" });
    const data = await response.json();
    groups = data.stickers || [];
    renderPicker();
  } catch (_) {
    groups = [];
  }
}

function renderPicker() {
  if (!dom.stickerPicker) return;
  dom.stickerPicker.replaceChildren();
  for (const group of groups) {
    for (const filename of group.images || []) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sticker-option";
      button.title = group.emotion;
      const image = document.createElement("img");
      image.src = `/api/stickers/file/${encodeURIComponent(group.pack)}/${encodeURIComponent(group.emotion)}/${encodeURIComponent(filename)}`;
      image.alt = group.emotion;
      button.appendChild(image);
      button.addEventListener("click", () => {
        state.pendingSticker = {
          pack: group.pack,
          emotion: group.emotion,
          filename,
          url: image.src,
        };
        dom.input.value = `[表情：${group.emotion}]`;
        dom.stickerPicker.hidden = true;
        sendMessage();
      });
      dom.stickerPicker.appendChild(button);
    }
  }
}

export function bindStickers() {
  if (!dom.btnSticker || dom.btnSticker.dataset.bound === "1") return;
  dom.btnSticker.dataset.bound = "1";
  dom.btnSticker.addEventListener("click", async () => {
    if (!groups.length) await loadStickers();
    if (!groups.length) {
      toast("暂无可用表情包");
      return;
    }
    dom.stickerPicker.hidden = !dom.stickerPicker.hidden;
  });
}
