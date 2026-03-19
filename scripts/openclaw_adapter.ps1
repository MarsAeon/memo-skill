$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..

$python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python executable not found at $python"
}

if ($args.Count -gt 0) {
  $request = $args[0]
  & $python .\src\openclaw_adapter.py --request $request
} else {
  $stdin = [Console]::In.ReadToEnd().Trim()
  if ([string]::IsNullOrWhiteSpace($stdin)) {
    throw "No request provided. Pass JSON arg or stdin."
  }
  & $python .\src\openclaw_adapter.py --request $stdin
}
