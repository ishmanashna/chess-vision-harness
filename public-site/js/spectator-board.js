/**
 * Read-only cm-chessboard for /g/ spectator view.
 * Position from start_fen + plies_detail replay (chess.js); never agent APIs.
 */

import {
  Chessboard,
  COLOR,
  BORDER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";
import {
  Markers,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/markers/Markers.js";
import { Arrows } from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/arrows/Arrows.js";
import { Chess } from "https://cdn.jsdelivr.net/npm/chess.js@1.4.0/dist/esm/chess.js";
import { createBoardAnnotations } from "./board-annotations.js";
import { paintLastMoveMarkers } from "./board-last-move.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

function fenAtPly(startFen, plies, ply) {
  const chess = new Chess(startFen || START_FEN);
  const n = Math.max(0, Math.min(ply, plies.length));
  for (let i = 0; i < n; i++) {
    const p = plies[i];
    if (!p) break;
    let ok = null;
    if (p.san) {
      try {
        ok = chess.move(p.san);
      } catch (_) {
        ok = null;
      }
    }
    if (!ok && p.uci && p.uci.length >= 4) {
      const moveObj = {
        from: p.uci.slice(0, 2),
        to: p.uci.slice(2, 4),
      };
      if (p.uci.length > 4) moveObj.promotion = p.uci[4];
      try {
        ok = chess.move(moveObj);
      } catch (_) {
        ok = null;
      }
    }
    if (!ok) break;
  }
  return chess.fen();
}

function lastMoveUciAtViewPly(plies, viewPly) {
  if (viewPly <= 0) return null;
  const ply = plies[viewPly - 1];
  return ply && ply.uci ? ply.uci : null;
}

/**
 * @param {HTMLElement} mountEl
 * @returns {{
 *   syncTip: (startFen: string|null|undefined, pliesDetail: Array, animate?: boolean) => Promise<void>,
 *   setViewPly: (ply: number, animate?: boolean) => Promise<void>,
 *   getViewPly: () => number,
 *   getTipPly: () => number,
 *   destroy: () => void,
 * }}
 */
export function createSpectatorBoard(mountEl) {
  let startFen = START_FEN;
  let pliesDetail = [];
  let tipPly = 0;
  let viewPly = 0;
  let lastAppliedFen = null;

  const board = new Chessboard(mountEl, {
    position: startFen,
    assetsUrl: BOARD_ASSETS,
    orientation: COLOR.white,
    responsive: true,
    style: {
      borderType: BORDER_TYPE.none,
      showCoordinates: true,
      pieces: { file: "pieces/staunty.svg" },
      animationDuration: 200,
    },
    extensions: [
      {
        class: Markers,
        props: { autoMarkers: null },
      },
      { class: Arrows },
    ],
  });

  const annotations = createBoardAnnotations(board);

  function paintLastMoveForView() {
    paintLastMoveMarkers(board, lastMoveUciAtViewPly(pliesDetail, viewPly));
  }

  /** cm-chessboard can mount at 0×0; nudge once layout has real dimensions. */
  function refreshLayout() {
    try {
      if (board.view && typeof board.view.handleResize === "function") {
        board.view.handleResize();
      }
    } catch (_) {
      /* ignore */
    }
  }

  function afterLayoutPaint() {
    refreshLayout();
    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        refreshLayout();
        requestAnimationFrame(resolve);
      });
    });
  }

  function applyPosition(animate) {
    annotations.clearAnnotations();
    const fen = fenAtPly(startFen, pliesDetail, viewPly);
    const doAnimate = !!animate && lastAppliedFen != null && fen !== lastAppliedFen;
    lastAppliedFen = fen;
    return board
      .setPosition(fen, doAnimate)
      .then(() => {
        paintLastMoveForView();
      })
      .then(() => afterLayoutPaint());
  }

  function syncTip(nextStartFen, nextPlies, animate) {
    startFen = nextStartFen || START_FEN;
    pliesDetail = Array.isArray(nextPlies) ? nextPlies : [];
    tipPly = pliesDetail.length;
    viewPly = tipPly;
    return applyPosition(animate);
  }

  /** Phase 7 hook: scrub to a historical ply (0 = start). */
  function setViewPly(ply, animate) {
    const n = Math.max(0, Math.min(Number(ply) || 0, pliesDetail.length));
    viewPly = n;
    return applyPosition(animate);
  }

  function destroy() {
    annotations.destroy();
    try {
      board.destroy();
    } catch (_) {
      /* ignore */
    }
  }

  return {
    syncTip,
    setViewPly,
    getViewPly: () => viewPly,
    getTipPly: () => tipPly,
    destroy,
  };
}
