@echo off
echo Starting Chess Vision Harness Spectator...
echo Open http://localhost:8765 in your browser
echo Stop with Ctrl+C, or run: python play.py serve stop
cd /d "%~dp0"
python play.py serve %*
