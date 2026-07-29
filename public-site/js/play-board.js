/**
 * cm-chessboard widget — client chess.js is UX only; server validates moves.
 */

import {
  Chessboard,
  COLOR,
  INPUT_EVENT_TYPE,
  BORDER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";
import {
  Markers,
  MARKER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/markers/Markers.js";
import {
  PromotionDialog,
  PROMOTION_DIALOG_RESULT_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/promotion-dialog/PromotionDialog.js";
import { Chess } from "https://cdn.jsdelivr.net/npm/chess.js@1.0.0-beta.6/dist/chess.js";
import { uciFromSquares } from "./play-api.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";

export function createPlayBoard(mountEl, humanColor, onSubmitMove) {
  const chess = new Chess();
  let legalUci = [];
  let inputEnabled = false;
  let pendingUci = null;
  let promoDialogOpen = false;
  let humanSide = humanColor === "black" ? COLOR.black : COLOR.white;

  const board = new Chessboard(mountEl, {
    position: chess.fen(),
    assetsUrl: BOARD_ASSETS,
    orientation: humanSide,
    style: {
      borderType: BORDER_TYPE.none,
      pieces: { file: "pieces/staunty.svg" },
      animationDuration: 200,
    },
    extensions: [
      { class: Markers, props: { autoMarkers: MARKER_TYPE.frame } },
      { class: PromotionDialog },
    ],
  });

  function syncLegalUci(list) {
    legalUci = Array.isArray(list) ? list.slice() : [];
  }

  function isServerLegal(from, to, promotion) {
    const uci = uciFromSquares(from, to, promotion);
    if (legalUci.includes(uci)) return true;
    const base = from + to;
    if (!promotion && legalUci.some((m) => m.startsWith(base) && m.length === 5)) {
      return true;
    }
    return false;
  }

  function applyInputState(canMove) {
    inputEnabled = !!canMove;
    if (canMove) {
      board.enableMoveInput(inputHandler, humanSide);
    } else {
      board.disableMoveInput();
    }
  }

  function setPosition(fen, animate) {
    chess.load(fen);
    pendingUci = null;
    return board.setPosition(fen, !!animate);
  }

  function finishLocalMove(from, to, promotion) {
    const needsPromo = legalUci.some(
      (m) => m.startsWith(from + to) && m.length === 5
    );
    if (needsPromo && !promotion) return null;
    const moveObj = { from, to };
    if (promotion) moveObj.promotion = promotion;
    const result = chess.move(moveObj);
    if (!result) return null;
    const uci = uciFromSquares(from, to, promotion);
    if (!isServerLegal(from, to, promotion)) return null;
    pendingUci = uci;
    return uci;
  }

  async function submitPending() {
    if (!pendingUci) return;
    const uci = pendingUci;
    pendingUci = null;
    applyInputState(false);
    const ok = await onSubmitMove(uci, chess.fen());
    if (!ok) {
      /* parent re-syncs FEN */
    }
  }

  function inputHandler(event) {
    if (event.type === INPUT_EVENT_TYPE.movingOverSquare) return;
    if (event.type !== INPUT_EVENT_TYPE.moveInputFinished) {
      event.chessboard.removeLegalMovesMarkers();
    }
    if (!inputEnabled) return false;

    if (event.type === INPUT_EVENT_TYPE.moveInputStarted) {
      const moves = chess.moves({ square: event.squareFrom, verbose: true });
      event.chessboard.addLegalMovesMarkers(moves);
      return moves.length > 0;
    }

    if (event.type === INPUT_EVENT_TYPE.validateMoveInput) {
      pendingUci = null;
      promoDialogOpen = false;
      const from = event.squareFrom;
      const to = event.squareTo;
      const uci = finishLocalMove(from, to, event.promotion || undefined);
      if (uci) {
        event.chessboard.state.moveInputProcess.then(() => {
          board.setPosition(chess.fen(), true);
        });
        return true;
      }

      const candidates = chess.moves({ square: from, verbose: true });
      const needsPromo = candidates.some((m) => m.promotion && m.to === to);
      if (needsPromo) {
        promoDialogOpen = true;
        const promoColor =
          humanSide === COLOR.white ? COLOR.white : COLOR.black;
        event.chessboard.showPromotionDialog(to, promoColor, (result) => {
          promoDialogOpen = false;
          if (result.type === PROMOTION_DIALOG_RESULT_TYPE.pieceSelected) {
            const piece = result.piece.charAt(1).toLowerCase();
            const ok = finishLocalMove(from, to, piece);
            if (ok) {
              board.setPosition(chess.fen(), true).then(() => submitPending());
            } else {
              board.setPosition(chess.fen(), false);
              applyInputState(true);
            }
          } else {
            pendingUci = null;
            board.setPosition(chess.fen(), false);
            applyInputState(true);
          }
        });
        return true;
      }
      return false;
    }

    if (event.type === INPUT_EVENT_TYPE.moveInputFinished) {
      if (!promoDialogOpen && event.legalMove && pendingUci) {
        submitPending();
      }
    }
    return false;
  }

  return {
    setPosition,
    syncLegalUci,
    setHumanColor(color) {
      humanSide = color === "black" ? COLOR.black : COLOR.white;
      board.setOrientation(humanSide);
    },
    applyInputState,
  };
}
