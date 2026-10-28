# Ragnarok - executa a interface web (sem argumentos) ou qualquer comando: .\run.ps1 say "texto" --out a.mp3
$vpy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $vpy)) { Write-Host "Rode install.ps1 primeiro." -ForegroundColor Red; exit 1 }
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $PSScriptRoot
if ($args.Count -eq 0) { $args = @('web') }
& $vpy -m ragnarok @args
exit $LASTEXITCODE
