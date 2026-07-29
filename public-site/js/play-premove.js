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
 * On turn edge, auto-submit queued premove if still legal; else clear quietly.
 * Returns position payload when a premove POST succeeded (caller should re-sync).
 */
export async function tryFirePremove(board, api, pos, prevYourTurn) {
  if (prevYourTurn !== false || !pos.your_turn || pos.game_over) return false;
  const uci = board.getPremove();
  if (!uci) return false;
  const legal = pos.legal_moves_uci || [];
  const resolved = resolvePremoveUci(uci, legal);
  if (!resolved) {
    board.clearPremove();
    return false;
  }
  board.clearPremove();
  board.syncInputState(false, false);
  const res = await api.postMove(resolved);
  return res;
}
