@echo off
cd /d "%~dp0"
echo Lantern Deck will send configured keyboard shortcuts to Windows.
echo Close this window to stop. Test with harmless shortcuts before use.
python server.py --enable-keys
pause
