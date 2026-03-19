$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..

$python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python executable not found at $python"
}

& $python .\src\memo_skill.py scan-due
