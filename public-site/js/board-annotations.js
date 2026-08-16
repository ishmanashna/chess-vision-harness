/**
 * Lichess-style board annotations: right-click-drag arrow, right-click square mark,
 * left-click clear. Uses cm-chessboard 8.7.2 Arrows + Markers (not persisted).
 */

import { ARROW_TYPE } from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/arrows/Arrows.js";

export const ANNOTATION_ARROW_TYPE = ARROW_TYPE.default;

export const ANNOTATION_PREVIEW_ARROW_TYPE = {
  class: "arrow-annotation-preview",
  slice: "arrowDefault",
  headSize: 7,
};

export const ANNOTATION_SQUARE_MARKER = {
  class: "annotation-square",
  slice: "markerSquare",
};

/**
 * @param {import("https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js").Chessboard} chessboard
 * @param {{ isInteractionBlocked?: () => boolean }} [options]
 */
export function createBoardAnnotations(chessboard, options = {}) {
  const blocked =
    typeof options.isInteractionBlocked === "function"
      ? options.isInteractionBlocked
      : () => false;
  const ctx = chessboard.context;
  let dragStart = null;
  let previewActive = false;

  function clearAnnotations() {
    chessboard.removeArrows(ANNOTATION_ARROW_TYPE);
    chessboard.removeArrows(ANNOTATION_PREVIEW_ARROW_TYPE);
    chessboard.removeMarkers(ANNOTATION_SQUARE_MARKER);
    previewActive = false;
    dragStart = null;
  }

  function findSquare(event) {
    const target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-square")) {
      return target.getAttribute("data-square");
    }
    const el = target && target.closest && target.closest("[data-square]");
    return el ? el.getAttribute("data-square") : null;
  }

  function removePreview() {
    if (!previewActive) return;
    chessboard.removeArrows(ANNOTATION_PREVIEW_ARROW_TYPE);
    previewActive = false;
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  function onMouseDown(event) {
    if (event.button === 0) {
      if (!blocked()) clearAnnotations();
      return;
    }
    if (event.button !== 2 || blocked()) return;
    const square = findSquare(event);
    if (square) dragStart = square;
  }

  function onMouseMove(event) {
    if (!dragStart) return;
    const toSquare = findSquare(event);
    if (!toSquare || toSquare === dragStart) {
      removePreview();
      return;
    }
    chessboard.removeArrows(ANNOTATION_PREVIEW_ARROW_TYPE);
    chessboard.addArrow(ANNOTATION_PREVIEW_ARROW_TYPE, dragStart, toSquare);
    previewActive = true;
  }

  function onMouseUp(event) {
    removePreview();
    if (!dragStart || event.button !== 2) {
      dragStart = null;
      return;
    }
    const endSquare = findSquare(event) || dragStart;
    if (!blocked()) {
      if (dragStart !== endSquare) {
        chessboard.addArrow(ANNOTATION_ARROW_TYPE, dragStart, endSquare);
      } else {
        chessboard.addMarker(ANNOTATION_SQUARE_MARKER, dragStart);
      }
    }
    dragStart = null;
  }

  const bindings = [
    ["contextmenu", onContextMenu],
    ["mousedown", onMouseDown],
    ["mousemove", onMouseMove],
    ["mouseup", onMouseUp],
    ["mouseleave", onMouseUp],
  ];

  bindings.forEach(([name, fn]) => ctx.addEventListener(name, fn));

  return {
    clearAnnotations,
    destroy() {
      bindings.forEach(([name, fn]) => ctx.removeEventListener(name, fn));
    },
  };
}
