@echo off
REM Installe Plan Move sous Windows.
REM tippecanoe (generation des cartes) n'a pas de version Windows native :
REM l'installation passe par WSL (Windows Subsystem for Linux).
setlocal
cd /d "%~dp0"

where wsl >nul 2>nul
if %errorlevel%==0 (
  echo [Plan Move] WSL detecte : installation dans le sous-systeme Linux...
  echo.
  wsl bash ./install.sh %*
  goto :end
)

echo [Plan Move] WSL n'est pas installe sur cette machine.
echo.
echo   tippecanoe, qui genere les fonds de carte, n'existe pas en version
echo   Windows native. L'installation se fait donc via WSL (Linux sous Windows).
echo.
echo   1) Ouvrez PowerShell EN ADMINISTRATEUR et lancez :   wsl --install
echo   2) Redemarrez le PC, ouvrez "Ubuntu" une premiere fois.
echo   3) Relancez ce fichier install.bat.
echo.
echo   Aide : https://learn.microsoft.com/windows/wsl/install
echo.
pause

:end
endlocal
