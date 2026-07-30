/** Download human-oriented board PNG after game over. */

export async function exportBoardPngBlob(mountEl) {
  const svg = mountEl.querySelector("svg");
  if (!svg) return null;
  const rect = svg.getBoundingClientRect();
  const size = Math.max(Math.round(rect.width), 400);
  const clone = svg.cloneNode(true);
  clone.setAttribute("width", String(size));
  clone.setAttribute("height", String(size));
  const svgStr = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(
    new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" })
  );
  try {
    const img = await new Promise((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = reject;
      el.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, size, size);
    ctx.drawImage(img, 0, 0, size, size);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  } catch (_e) {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function setupBoardDownload(root, board, api, gameId) {
  const btn = root.querySelector("[data-download-board]");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const filename = `${gameId}-position.png`;
    try {
      let blob = null;
      if (board.exportPngBlob) {
        blob = await board.exportPngBlob();
      }
      if (!blob) {
        blob = await api.fetchBoardPng();
      }
      if (blob) triggerDownload(blob, filename);
    } catch (_err) {
      try {
        const blob = await api.fetchBoardPng();
        if (blob) triggerDownload(blob, filename);
      } catch (_e2) {
        /* ignore */
      }
    } finally {
      btn.disabled = false;
    }
  });
}

export function syncDownloadButton(root, pos) {
  const btn = root.querySelector("[data-download-board]");
  const slot = root.querySelector("[data-download-slot]");
  if (!btn) return;
  const show = !!pos.game_over;
  btn.hidden = !show;
  btn.disabled = !show;
  if (slot) slot.hidden = !show;
}
