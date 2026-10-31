@echo off
rem One-click local ops dashboard: starts the server in a minimized WSL window and opens the browser.
rem Close the "Cascade Ops server" window to stop it.
start "Cascade Ops server" /min wsl -d Ubuntu -- bash -c "cd /mnt/d/CODE/Bittensor/cascade/cascade && pkill -f tools/dashboard/local; exec .claude-work/venv/bin/python -I tools/dashboard/local_v2.py --root ."
timeout /t 4 /nobreak >nul
start "" http://localhost:8791/
