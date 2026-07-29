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
import { Chess } from "https://cdn.jsdelivr.net/npm/chess.js@1.4.0/dist/esm/chess.js";
import { uciFromSquares } from "./play-api.js";
import { createPremoveController, PREMOVE_MARKER } from "./play-board-premove.js";
import { exportBoardPngBlob } from "./play-export.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";

const INPUT_MODE = {
  none: "none",
  move: "move",
  premove: "premove",
};

export function createPlayBoard(mountEl, humanColor, onSubmitMove) {
  const chess = new Chess();
  let legalUci = [];
  const inputEnabledRef = { current: false };
  let pendingUci = null;
  let promoDialogOpen = false;
  let humanSide = humanColor === "black" ? COLOR.black : COLOR.white;
  let displayedFen = chess.fen();

  let activeInputMode = INPUT_MODE.none;
  let desiredMove = false;
  let desiredPremove = false;

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
      {
        class: Markers,
        props: { autoMarkers: MARKER_TYPE.frame, customMarkers: [PREMOVE_MARKER] },
      },
      { class: PromotionDialog },
    ],
  });

  const premove = createPremoveController(board, chess, humanSide, () => {
    resumeInput();
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

  function isPromoDialogOpen() {
    return promoDialogOpen || premove.isPromoDialogOpen();
  }

  function targetInputMode() {
    if (desiredMove) return INPUT_MODE.move;
    if (desiredPremove) return INPUT_MODE.premove;
    return INPUT_MODE.none;
  }

  function disableLibraryInput() {
    if (isPromoDialogOpen()) return;
    if (!board.isMoveInputEnabled()) {
      activeInputMode = INPUT_MODE.none;
      inputEnabledRef.current = false;
      premove.setInputActive(false);
      return;
    }
    if (activeInputMode === INPUT_MODE.premove) {
      premove.onInputDisabled();
    }
    board.disableMoveInput();
    activeInputMode = INPUT_MODE.none;
    inputEnabledRef.current = false;
    premove.setInputActive(false);
  }

  function inputEnableError(err) {
    const msg = err && err.message ? err.message : String(err);
    if (msg.includes("already enabled")) {
      return "Board input is stuck; refresh the page.";
    }
    return `Board input failed: ${msg}`;
  }

  function enableLibraryInput(handler, mode) {
    try {
      board.enableMoveInput(handler, humanSide);
    } catch (err) {
      const msg = err && err.message ? err.message : String(err);
      if (!msg.includes("already enabled")) {
        return inputEnableError(err);
      }
      board.disableMoveInput();
      try {
        board.enableMoveInput(handler, humanSide);
      } catch (retryErr) {
        return inputEnableError(retryErr);
      }
    }
    activeInputMode = mode;
    inputEnabledRef.current = mode === INPUT_MODE.move;
    premove.setInputActive(mode === INPUT_MODE.premove);
    return null;
  }

  function applyDesiredInputState() {
    const want = targetInputMode();

    if (want === INPUT_MODE.none) {
      if (activeInputMode === INPUT_MODE.none && !board.isMoveInputEnabled()) {
        return null;
      }
      disableLibraryInput();
      return null;
    }

    if (isPromoDialogOpen()) return null;

    if (want === activeInputMode && board.isMoveInputEnabled()) {
      return null;
    }

    if (board.isMoveInputEnabled()) {
      if (activeInputMode === INPUT_MODE.premove) {
        premove.onInputDisabled();
      }
      board.disableMoveInput();
    }
    activeInputMode = INPUT_MODE.none;
    inputEnabledRef.current = false;
    premove.setInputActive(false);

    const handler =
      want === INPUT_MODE.move ? inputHandler : premove.premoveHandler;
    return enableLibraryInput(handler, want);
  }

  function syncInputState(canMove, canPremove) {
    desiredMove = !!canMove;
    desiredPremove = !!canPremove;
    return applyDesiredInputState();
  }

  function suspendInput() {
    disableLibraryInput();
  }

  function resumeInput() {
    return applyDesiredInputState();
  }

  function setPosition(fen, animate) {
    if (fen === displayedFen) return Promise.resolve();
    displayedFen = fen;
    chess.load(fen);
    pendingUci = null;
    return board.setPosition(fen, !!animate).then(() => premove.refreshMarkers());
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
    suspendInput();
    await onSubmitMove(uci, chess.fen());
  }

  function inputHandler(event) {
    if (event.type === INPUT_EVENT_TYPE.movingOverSquare) return;
    if (event.type !== INPUT_EVENT_TYPE.moveInputFinished) {
      event.chessboard.removeLegalMovesMarkers();
    }
    if (!inputEnabledRef.current) return false;

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
              resumeInput();
            }
          } else {
            pendingUci = null;
            board.setPosition(chess.fen(), false);
            resumeInput();
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

  mountEl.addEventListener("contextmenu", premove.onContextMenu);

  return {
    setPosition,
    syncLegalUci,
    setHumanColor(color) {
      const side = color === "black" ? COLOR.black : COLOR.white;
      if (side === humanSide) return;
      humanSide = side;
      board.setOrientation(humanSide);
    },
    syncInputState,
    getPremove: premove.getPremove,
    clearPremove: premove.clearPremove,
    exportPngBlob: () => exportBoardPngBlob(mountEl),
  };
}
