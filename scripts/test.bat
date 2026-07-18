@echo off
echo Running tests...
cd /d "%~dp0\..\python"
python -m pytest tests -v
