/** Premove input + markers for cm-chessboard play widget. */

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

export function createPremoveController(board, chess, humanSide) {
  let premoveEnabled = false;
  let premoveUci = null;
  let promoDialogOpen = false;

  function humanPieceChar() {
    return humanSide === COLOR.white ? "w" : "b";
  }

  function boardWithHumanToMove() {
    const tmp = new Chess(chess.fen());
    const parts = tmp.fen().split(" ");
    parts[1] = humanPieceChar();
    tmp.load(parts.join(" "));
    return tmp;
  }

  function clearPremoveMarkers() {
    board.removeMarkers(PREMOVE_MARKER.id);
  }

  function showPremoveMarkers(from, to) {
    clearPremoveMarkers();
    board.addMarker(from, PREMOVE_MARKER.id);
    board.addMarker(to, PREMOVE_MARKER.id);
  }

  function tryPremoveUci(from, to, promotion) {
    const tmp = boardWithHumanToMove();
    const moveObj = { from, to };
    if (promotion) moveObj.promotion = promotion;
    const result = tmp.move(moveObj);
    if (!result) return null;
    return uciFromSquares(from, to, promotion);
  }

  function setPremove(from, to, promotion) {
    const uci = tryPremoveUci(from, to, promotion);
    if (!uci) return false;
    premoveUci = uci;
    showPremoveMarkers(from, to);
    return true;
  }

  function clearPremove() {
    premoveUci = null;
    clearPremoveMarkers();
  }

  function refreshMarkers() {
    if (!premoveUci) return;
    showPremoveMarkers(premoveUci.slice(0, 2), premoveUci.slice(2, 4));
  }

  function applyPremoveInputState(canPremove, inputEnabledRef) {
    const want = !!canPremove;
    if (want === premoveEnabled) return;
    premoveEnabled = want;
    if (want) {
      inputEnabledRef.current = false;
      board.enableMoveInput(premoveHandler, humanSide);
    } else if (!inputEnabledRef.current) {
      board.disableMoveInput();
      if (!premoveUci) clearPremoveMarkers();
    }
  }

  function premoveHandler(event) {
    if (event.type === INPUT_EVENT_TYPE.movingOverSquare) return;
    if (event.type !== INPUT_EVENT_TYPE.moveInputFinished) {
      event.chessboard.removeLegalMovesMarkers();
    }
    if (!premoveEnabled) return false;

    if (event.type === INPUT_EVENT_TYPE.moveInputStarted) {
      const piece = chess.get(event.squareFrom);
      if (!piece || piece.color !== humanPieceChar()) return false;
      const tmp = boardWithHumanToMove();
      const moves = tmp.moves({ square: event.squareFrom, verbose: true });
      event.chessboard.addLegalMovesMarkers(moves);
      return moves.length > 0;
    }

    if (event.type === INPUT_EVENT_TYPE.validateMoveInput) {
      promoDialogOpen = false;
      const from = event.squareFrom;
      const to = event.squareTo;
      if (setPremove(from, to, event.promotion || undefined)) return true;

      const tmp = boardWithHumanToMove();
      const candidates = tmp.moves({ square: from, verbose: true });
      const needsPromo = candidates.some((m) => m.promotion && m.to === to);
      if (needsPromo) {
        promoDialogOpen = true;
        const promoColor =
          humanSide === COLOR.white ? COLOR.white : COLOR.black;
        event.chessboard.showPromotionDialog(to, promoColor, (result) => {
          promoDialogOpen = false;
          if (result.type === PROMOTION_DIALOG_RESULT_TYPE.pieceSelected) {
            const piece = result.piece.charAt(1).toLowerCase();
            setPremove(from, to, piece);
          }
        });
        return true;
      }
      return false;
    }

    return false;
  }

  return {
    applyPremoveInputState,
    getPremove: () => premoveUci,
    clearPremove,
    refreshMarkers,
    onContextMenu: (e) => {
      if (premoveUci) {
        e.preventDefault();
        clearPremove();
      }
    },
  };
}
