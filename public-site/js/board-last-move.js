/**
 * Theme-aware filled-square last-move highlights (from / to).
 */

import { Chess } from "https://cdn.jsdelivr.net/npm/chess.js@1.4.0/dist/esm/chess.js";

export const LAST_MOVE_FROM_MARKER = {
  class: "last-move-from",
  slice: "markerSquare",
};

export const LAST_MOVE_TO_MARKER = {
  class: "last-move-to",
  slice: "markerSquare",
};

export function squaresFromUci(uci) {
  if (!uci || uci.length < 4) return null;
  return { from: uci.slice(0, 2), to: uci.slice(2, 4) };
}

export function removeLastMoveMarkers(board) {
  board.removeMarkers(LAST_MOVE_FROM_MARKER);
  board.removeMarkers(LAST_MOVE_TO_MARKER);
}

export function paintLastMoveMarkers(board, uci) {
  removeLastMoveMarkers(board);
  const sq = squaresFromUci(uci);
  if (!sq) return;
  board.addMarker(LAST_MOVE_FROM_MARKER, sq.from);
  board.addMarker(LAST_MOVE_TO_MARKER, sq.to);
}

/** Replay SAN move rows from the start position to derive the last UCI at ply. */
export function lastUciFromMoveRows(moveRows, plyCount) {
  const ply = Number(plyCount) || 0;
  if (!ply || !Array.isArray(moveRows) || !moveRows.length) return null;

  const chess = new Chess();
  let lastUci = null;
  let seen = 0;

  for (const row of moveRows) {
    if (seen >= ply) break;
    if (row.white) {
      const m = chess.move(row.white);
      if (!m) break;
      lastUci = m.from + m.to + (m.promotion || "");
      seen++;
      if (seen >= ply) break;
    }
    if (seen >= ply) break;
    if (row.black) {
      const m = chess.move(row.black);
      if (!m) break;
      lastUci = m.from + m.to + (m.promotion || "");
      seen++;
    }
  }

  return lastUci;
}
