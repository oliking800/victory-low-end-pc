@echo off
rem victory-easy: one friendly env file, one command.
rem Create victory-easy.env from victory-easy.env.example and set GAME.
setlocal
set "TOOL=%~dp0tools\victory_easy.py"
python "%TOOL%" %*
if errorlevel 9009 py -3 "%TOOL%" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
