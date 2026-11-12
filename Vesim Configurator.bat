@echo off
rem Launches the Vesim Configurator (needs Python 3 with Tkinter, the standard python.org install has it)
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw vesim_configurator.py) || (python vesim_configurator.py & pause)
