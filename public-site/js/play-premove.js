/** Client-only premove turn-edge handling for human play. */

export function canPremove(pos) {
  return !pos.game_over && pos.agent_joined && !pos.your_turn;
}

function resolvePremoveUci(uci, legal) {
  if (!uci || !legal.length) return null;
  if (legal.includes(uci)) return uci;
  const base = uci.slice(0, 4);
  if (uci.length === 4) {
    const promos = legal.filter((m) => m.startsWith(base) && m.length === 5);
    if (promos.length === 1) return promos[0];
  }
  return null;
}

/**
 * On turn edge, fire queued premove heads while it is still your turn.
 * Illegal heads are dropped quietly; the next head is tried.
 * Returns position payload when at least one premove POST succeeded.
 */
export async function tryFirePremove(board, api, pos, prevYourTurn) {
  if (prevYourTurn !== false || !pos.your_turn || pos.game_over) return false;

  let current = pos;
  let anyFired = false;

  while (current.your_turn && !current.game_over) {
    const uci = board.peekPremove ? board.peekPremove() : board.getPremove();
    if (!uci) break;

    const legal = current.legal_moves_uci || [];
    const resolved = resolvePremoveUci(uci, legal);
    if (!resolved) {
      if (board.dequeuePremove) board.dequeuePremove();
      else board.clearPremove();
      continue;
    }

    // Skip ghost refresh until setPosition after POST (avoids a flash without this ply).
    if (board.dequeuePremove) board.dequeuePremove(true);
    else board.clearPremove();
    board.syncInputState(false, false);
    current = await api.postMove(resolved);
    anyFired = true;

    board.syncLegalUci(current.legal_moves_uci);
    if (current.fen) {
      await board.setPosition(current.fen, true);
    }
  }

  return anyFired ? current : false;
}
