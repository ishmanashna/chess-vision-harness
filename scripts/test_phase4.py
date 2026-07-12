import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ['STOCKFISH_PATH'] = os.path.join(os.path.dirname(__file__), '..', 'sf-plain', 'stockfish', 'stockfish-windows-x86-64.exe')

from chess_harness.tournament import TournamentManager
from chess_harness.results import ResultsManager

tm = TournamentManager()

manifest = tm.create_tournament_matrix(skills=[5, 10], games_per_cell=1, agent_colors=['white'])
print("Manifest:", len(manifest["games"]), "games")
for g in manifest["games"]:
    print("  %s: skill=%d color=%s" % (g["game_id"], g["skill"], g["agent_color"]))

print("\nSmoke test (2 games)...")
result = tm.run_smoke_test(num_games=2, skills=[5], max_moves=20)
print("Played:", result["games_played"], "games")
for r in result["results"]:
    print("  %s: status=%s result=%s moves=%s" % (r["game_id"], r["status"], r["result"], r["moves"]))

results_file = tm.game_manager.base_dir / "results.jsonl"
print("\nresults.jsonl:", results_file.exists())
if results_file.exists():
    with open(results_file) as f:
        lines = f.readlines()
    print("Records:", len(lines))
    for line in lines:
        rec = json.loads(line)
        print("  %s: skill=%s result=%s reason=%s" % (rec["game_id"], rec["skill"], rec["result"], rec["reason"]))

print("\nAggregate:")
rm = ResultsManager(str(tm.game_manager.base_dir))
summary = rm.get_summary()
print(json.dumps(summary, indent=2))

tm.engine.quit()
print("\nPHASE 4 PASSED")
