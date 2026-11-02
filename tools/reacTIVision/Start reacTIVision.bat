@echo off
rem Starts the FaceTime -> Unity Video Capture bridge, which then launches reacTIVision.
cd /d "%~dp0"
python camera_bridge.py %*
if errorlevel 1 pause
