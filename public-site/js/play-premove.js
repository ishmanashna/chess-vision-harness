/** Client-only premove turn-edge handling for human play. */

export function canPremove(pos) {
  return !pos.game_over && pos.agent_joined && !pos.your_turn;
}

/**
 * On turn edge, auto-submit queued premove if still legal; else clear quietly.
 * Returns true when a premove POST was started (caller should await and re-sync).
 */
export async function tryFirePremove(board, api, pos, prevYourTurn) {
  if (prevYourTurn !== false || !pos.your_turn || pos.game_over) return false;
  const uci = board.getPremove();
  if (!uci) return false;
  const legal = pos.legal_moves_uci || [];
  if (!legal.includes(uci)) {
    board.clearPremove();
    return false;
  }
  board.clearPremove();
  const res = await api.postMove(uci);
  return res;
}
