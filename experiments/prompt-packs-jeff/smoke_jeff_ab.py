#!/usr/bin/env python3
"""Short smoke for Jeff A/B path (NOT the 35-game wave)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'python' / 'src'))
os.chdir(REPO)

KEY_FILE = Path(r'C:\Users\jordi\Desktop\coding stuff\keys\typesafe_api_key.txt')
HARNESS = 'http://127.0.0.1:8765'
MODEL = 'jev-latest'


def ensure_key() -> None:
    if os.environ.get('TYPESAFE_API_KEY', '').strip():
        return
    if KEY_FILE.is_file():
        os.environ['TYPESAFE_API_KEY'] = KEY_FILE.read_text(encoding='utf-8').strip()
    if not os.environ.get('TYPESAFE_API_KEY', '').strip():
        raise SystemExit(f'Missing TYPESAFE_API_KEY at {KEY_FILE}')


def main() -> int:
    ensure_key()
    from chess_harness.agent_http.client import AgentHttpClient
    from chess_harness.agent_http.transport import urllib_transport
    from chess_harness.prompt_packs import load_pack
    from chess_harness.prompt_test_ops import build_prompt_test_snapshot
    from chess_harness.runner.adapters import build_adapter_for_pack
    from chess_harness.runner.config import SlotConfig
    from chess_harness.runner.keys import ensure_harness_key
    from chess_harness.runner.log import RunnerLog
    from chess_harness.runner.paths import keys_path
    from chess_harness.runner.quota import QuotaTracker
    from chess_harness.runner.slot_worker import play_game

    pack_je = load_pack('je')
    print(f'je kind={pack_je.kind} seats={getattr(pack_je, "seat_packs", None)}')

    transport = urllib_transport()
    slot_je = SlotConfig(
        inscribed_id=MODEL,
        provider='typesafe',
        observation='text',
        provider_model=MODEL,
        base_url='https://api.typesafe.ai/v1',
        env_key='TYPESAFE_API_KEY',
        rpm=60,
        rpd=5000,
        kind='ave',
        opponent='stockfish-handicap:noise38',
        agent_color='white',
        prompt_pack='je',
    )
    adapter = build_adapter_for_pack(slot_je, transport, 'je')
    print(f'council adapter: {type(adapter).__name__}')

    slot_ja = SlotConfig(
        inscribed_id=MODEL,
        provider='typesafe',
        observation='text',
        provider_model=MODEL,
        base_url='https://api.typesafe.ai/v1',
        env_key='TYPESAFE_API_KEY',
        rpm=60,
        rpd=5000,
        kind='ave',
        opponent='stockfish-handicap:noise38',
        agent_color='white',
        prompt_pack='ja',
    )
    api_key = ensure_harness_key(
        base_url=HARNESS,
        inscribed_id=slot_ja.inscribed_id,
        observation=slot_ja.observation,
        transport=transport,
        path=keys_path(),
    )
    client = AgentHttpClient(
        HARNESS, api_key, model_id=slot_ja.inscribed_id, transport=transport
    )
    adapter_ja = build_adapter_for_pack(slot_ja, transport, 'ja')
    quota = QuotaTracker(rpm=60, rpd=5000)
    (HERE / 'runs').mkdir(parents=True, exist_ok=True)
    logger = RunnerLog(HERE / 'runs' / 'smoke.log')
    print('playing smoke ja vs noise38 (max_agent_plies=2)...')
    outcome = play_game(
        client, adapter_ja, slot_ja, quota, logger, max_agent_plies=2
    )
    print('smoke outcome:', outcome)

    snap = build_prompt_test_snapshot(family='jeff')
    packs = snap.get('packs') or []
    if isinstance(packs, dict):
        print('jeff packs:', list(packs.keys()))
    else:
        print('jeff packs:', [p.get('id') for p in packs])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
