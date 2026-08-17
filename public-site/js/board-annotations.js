/**
 * Lichess-style board annotations: right-click-drag arrow, right-click square
 * mark, left-click clear. Repeat click toggles. Knights use an L (two segments).
 * No drag preview. cm-chessboard 8.7.2 Arrows + Markers (not persisted).
 */

import { ARROW_TYPE } from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/arrows/Arrows.js";

export const ANNOTATION_ARROW_TYPE = ARROW_TYPE.default;

/** First leg of a knight L: same stroke, no arrowhead. */
export const ANNOTATION_ARROW_SHAFT_TYPE = {
  class: "arrow-annotation-shaft",
  slice: "arrowDefault",
  headSize: 0,
};

export const ANNOTATION_SQUARE_MARKER = {
  class: "annotation-square",
  slice: "markerSquare",
};

function fileIndex(square) {
  return square.charCodeAt(0) - 97;
}

function rankIndex(square) {
  return square.charCodeAt(1) - 49;
}

function squareFromIndexes(file, rank) {
  return String.fromCharCode(97 + file) + String.fromCharCode(49 + rank);
}

/** Knight geometry: (|df|,|dr|) is {1,2}. */
export function isKnightMove(from, to) {
  if (!from || !to || from === to) return false;
  const df = Math.abs(fileIndex(from) - fileIndex(to));
  const dr = Math.abs(rankIndex(from) - rankIndex(to));
  return (df === 1 && dr === 2) || (df === 2 && dr === 1);
}

/** Longer leg first (rank ±2 or file ±2), then the short step. */
export function knightCornerSquare(from, to) {
  if (!isKnightMove(from, to)) return null;
  const df = fileIndex(to) - fileIndex(from);
  const dr = rankIndex(to) - rankIndex(from);
  if (Math.abs(dr) === 2) {
    return squareFromIndexes(fileIndex(from), rankIndex(to));
  }
  return squareFromIndexes(fileIndex(to), rankIndex(from));
}

function arrowKey(from, to) {
  return from + to;
}

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
  /** @type {Set<string>} */
  const logicalArrows = new Set();

  function removeLogicalArrow(from, to) {
    const key = arrowKey(from, to);
    const corner = knightCornerSquare(from, to);
    let present = logicalArrows.has(key);
    if (!present && typeof chessboard.getArrows === "function") {
      if (corner) {
        const shaft = chessboard.getArrows(ANNOTATION_ARROW_SHAFT_TYPE, from, corner);
        const head = chessboard.getArrows(ANNOTATION_ARROW_TYPE, corner, to);
        present = !!(shaft && shaft.length && head && head.length);
      } else {
        const direct = chessboard.getArrows(ANNOTATION_ARROW_TYPE, from, to);
        present = !!(direct && direct.length);
      }
    }
    if (!present) return false;
    logicalArrows.delete(key);
    if (corner) {
      chessboard.removeArrows(ANNOTATION_ARROW_SHAFT_TYPE, from, corner);
      chessboard.removeArrows(ANNOTATION_ARROW_TYPE, corner, to);
    }
    chessboard.removeArrows(ANNOTATION_ARROW_TYPE, from, to);
    return true;
  }

  function addLogicalArrow(from, to) {
    const key = arrowKey(from, to);
    logicalArrows.add(key);
    const corner = knightCornerSquare(from, to);
    if (corner) {
      chessboard.addArrow(ANNOTATION_ARROW_SHAFT_TYPE, from, corner);
      chessboard.addArrow(ANNOTATION_ARROW_TYPE, corner, to);
      return;
    }
    chessboard.addArrow(ANNOTATION_ARROW_TYPE, from, to);
  }

  function toggleArrow(from, to) {
    if (removeLogicalArrow(from, to)) return;
    addLogicalArrow(from, to);
  }

  function toggleSquare(square) {
    const existing = chessboard.getMarkers(ANNOTATION_SQUARE_MARKER, square);
    if (existing && existing.length) {
      chessboard.removeMarkers(ANNOTATION_SQUARE_MARKER, square);
      return;
    }
    chessboard.addMarker(ANNOTATION_SQUARE_MARKER, square);
  }

  function clearAnnotations() {
    chessboard.removeArrows(ANNOTATION_ARROW_TYPE);
    chessboard.removeArrows(ANNOTATION_ARROW_SHAFT_TYPE);
    chessboard.removeMarkers(ANNOTATION_SQUARE_MARKER);
    logicalArrows.clear();
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

  function squareOccupied(square) {
    if (!square) return false;
    try {
      if (typeof chessboard.getPiece === "function") {
        return !!chessboard.getPiece(square);
      }
    } catch (_e) {
      /* ignore */
    }
    return false;
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  function onMouseDown(event) {
    if (event.button === 0) {
      if (!blocked()) {
        const square = findSquare(event);
        if (!squareOccupied(square)) clearAnnotations();
      }
      return;
    }
    if (event.button !== 2 || blocked()) return;
    const square = findSquare(event);
    if (square) dragStart = square;
  }

  function onMouseUp(event) {
    if (!dragStart || event.button !== 2) {
      dragStart = null;
      return;
    }
    const endSquare = findSquare(event) || dragStart;
    if (!blocked()) {
      if (dragStart !== endSquare) {
        toggleArrow(dragStart, endSquare);
      } else {
        toggleSquare(dragStart);
      }
    }
    dragStart = null;
  }

  const bindings = [
    ["contextmenu", onContextMenu],
    ["mousedown", onMouseDown],
    ["mouseup", onMouseUp],
    ["mouseleave", onMouseUp],
  ];

  bindings.forEach(([name, fn]) => ctx.addEventListener(name, fn));

  return {
    clearAnnotations,
    toggleArrow,
    toggleSquare,
    destroy() {
      bindings.forEach(([name, fn]) => ctx.removeEventListener(name, fn));
    },
  };
}
