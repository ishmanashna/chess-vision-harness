/** Multi-premove queue + ghost display for cm-chessboard play widget.
 *
 * Server `chess` stays truth. Queue is client-only. Ghost = virtual FEN from
 * server + queued plies via board.setPosition — never chess.load for ghosts.
 * Escape / right-click / Cancel clears the whole queue and restores server.
 */

import {
  INPUT_EVENT_TYPE,
  COLOR,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";
import {
  PROMOTION_DIALOG_RESULT_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/promotion-dialog/PromotionDialog.js";
import { uciFromSquares } from "./play-api.js";
import { Chess } from "https://cdn.jsdelivr.net/npm/chess.js@1.4.0/dist/esm/chess.js";

export const PREMOVE_MARKER = {
  id: "premove",
  class: "premove-marker",
  slice: "markerFrame",
};

function parseUci(uci) {
  return {
    from: uci.slice(0, 2),
    to: uci.slice(2, 4),
    promotion: uci.length > 4 ? uci[4] : undefined,
  };
}

export function createPremoveController(board, chess, getHumanSide, callbacks) {
  const onPromoDialogClosed =
    typeof callbacks === "function" ? callbacks : callbacks && callbacks.onPromoDialogClosed;
  const onPremoveChange =
    typeof callbacks === "object" && callbacks ? callbacks.onPremoveChange : null;

  let inputActive = false;
  /** @type {string[]} */
  let queue = [];
  let promoDialogOpen = false;
  let displayedFen = null;

  function humanSide() {
    return typeof getHumanSide === "function" ? getHumanSide() : getHumanSide;
  }

  function humanPieceChar() {
    return humanSide() === COLOR.white ? "w" : "b";
  }

  function forceHumanToMove(tmp) {
    const parts = tmp.fen().split(" ");
    parts[1] = humanPieceChar();
    tmp.load(parts.join(" "));
    return tmp;
  }

  function applyUci(tmp, uci) {
    const { from, to, promotion } = parseUci(uci);
    const moveObj = { from, to };
    if (promotion) moveObj.promotion = promotion;
    return tmp.move(moveObj);
  }

  /** Virtual board after all queued plies (human forced before each). */
  function virtualBoardFromQueue() {
    const tmp = new Chess(chess.fen());
    for (const uci of queue) {
      forceHumanToMove(tmp);
      if (!applyUci(tmp, uci)) break;
    }
    return tmp;
  }

  /** Board used to validate / show legal moves for the next enqueue. */
  function boardForNextPremove() {
    return forceHumanToMove(virtualBoardFromQueue());
  }

  function clearPremoveMarkers() {
    board.removeMarkers(PREMOVE_MARKER);
  }

  function showQueueMarkers() {
    clearPremoveMarkers();
    for (const uci of queue) {
      const { from } = parseUci(uci);
      board.addMarker(PREMOVE_MARKER, from);
    }
  }

  function notifyPremoveChange() {
    if (onPremoveChange) onPremoveChange(peek());
  }

  function targetDisplayFen() {
    if (!queue.length) return chess.fen();
    return virtualBoardFromQueue().fen();
  }

  function syncDisplay(animate) {
    const fen = targetDisplayFen();
    const doAnimate = !!animate;
    if (fen === displayedFen && !doAnimate) {
      showQueueMarkers();
      return Promise.resolve();
    }
    displayedFen = fen;
    return board.setPosition(fen, doAnimate).then(() => {
      showQueueMarkers();
    });
  }

  function tryPremoveUci(from, to, promotion) {
    const tmp = boardForNextPremove();
    const moveObj = { from, to };
    if (promotion) moveObj.promotion = promotion;
    const result = tmp.move(moveObj);
    if (!result) return null;
    return uciFromSquares(from, to, promotion);
  }

  function enqueue(from, to, promotion, opts) {
    const uci = tryPremoveUci(from, to, promotion);
    if (!uci) return false;
    queue.push(uci);
    notifyPremoveChange();
    if (!(opts && opts.skipDisplay)) {
      syncDisplay(!!(opts && opts.animate));
    }
    return true;
  }

  function afterDragCleanup(event, fn) {
    const proc =
      event.chessboard &&
      event.chessboard.state &&
      event.chessboard.state.moveInputProcess;
    if (proc && typeof proc.then === "function") {
      proc.then(fn);
      return;
    }
    fn();
  }

  function peek() {
    return queue.length ? queue[0] : null;
  }

  function dequeue(skipDisplay) {
    if (!queue.length) return null;
    const uci = queue.shift();
    if (!skipDisplay) syncDisplay(false);
    notifyPremoveChange();
    return uci;
  }

  function clear() {
    if (!queue.length) {
      clearPremoveMarkers();
      syncDisplay(false);
      return;
    }
    queue = [];
    clearPremoveMarkers();
    syncDisplay(false);
    notifyPremoveChange();
  }

  function onInputDisabled() {
    inputActive = false;
  }

  function premoveHandler(event) {
    if (event.type === INPUT_EVENT_TYPE.movingOverSquare) return;
    if (event.type !== INPUT_EVENT_TYPE.moveInputFinished) {
      event.chessboard.removeLegalMovesMarkers();
    }
    if (!inputActive) return false;

    if (event.type === INPUT_EVENT_TYPE.moveInputStarted) {
      const tmp = boardForNextPremove();
      const piece = tmp.get(event.squareFrom);
      if (!piece || piece.color !== humanPieceChar()) return false;
      const moves = tmp.moves({ square: event.squareFrom, verbose: true });
      event.chessboard.addLegalMovesMarkers(moves);
      return moves.length > 0;
    }

    if (event.type === INPUT_EVENT_TYPE.validateMoveInput) {
      promoDialogOpen = false;
      const from = event.squareFrom;
      const to = event.squareTo;

      // Enqueue but do not commit as a real widget move (return false).
      // Wait for drag-sprite teardown, then animate the ghost FEN.
      if (enqueue(from, to, event.promotion || undefined, { skipDisplay: true })) {
        afterDragCleanup(event, () => syncDisplay(true));
        return false;
      }

      const tmp = boardForNextPremove();
      const candidates = tmp.moves({ square: from, verbose: true });
      const needsPromo = candidates.some((m) => m.promotion && m.to === to);
      if (needsPromo) {
        promoDialogOpen = true;
        const promoColor =
          humanSide() === COLOR.white ? COLOR.white : COLOR.black;
        event.chessboard.showPromotionDialog(to, promoColor, (result) => {
          promoDialogOpen = false;
          if (result.type === PROMOTION_DIALOG_RESULT_TYPE.pieceSelected) {
            const piece = result.piece.charAt(1).toLowerCase();
            if (enqueue(from, to, piece, { skipDisplay: true })) {
              afterDragCleanup(event, () => syncDisplay(true));
            }
          }
          if (onPromoDialogClosed) onPromoDialogClosed();
        });
        return false;
      }
      return false;
    }

    return false;
  }

  function onKeyDown(e) {
    if (e.key === "Escape" && queue.length) {
      e.preventDefault();
      clear();
    }
  }

  return {
    premoveHandler,
    peek,
    dequeue,
    clear,
    getPremove: peek,
    clearPremove: clear,
    syncDisplay,
    setInputActive: (active) => {
      inputActive = !!active;
    },
    isPromoDialogOpen: () => promoDialogOpen,
    onInputDisabled,
    onContextMenu: (e) => {
      if (queue.length) {
        e.preventDefault();
        clear();
      }
    },
    onKeyDown,
  };
}
