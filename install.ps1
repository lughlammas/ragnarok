<#
  Ragnarok - instalador para Windows 10/11 (PowerShell 5.1+).
  Cria a pasta .venv, instala as dependências e baixa os modelos (Kokoro fp32 ~350 MB + Supertonic-3 ~400 MB).
  Uso:  powershell -ExecutionPolicy Bypass -File .\install.ps1     (ou dê duplo clique em install.bat)
#>
param([switch]$SkipTest)
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$localTemp = Join-Path $PSScriptRoot 'data\tmp'
New-Item -ItemType Directory -Force -Path $localTemp | Out-Null
$env:TEMP = $localTemp
$env:TMP = $localTemp

function Fail($msg) { Write-Host "ERRO: $msg" -ForegroundColor Red; exit 1 }

function Get-PythonExe {
    # 1) py launcher com versões suportadas (3.12, 3.11, 3.13); 2) python no PATH se for 3.11-3.13
    foreach ($v in '3.12', '3.11', '3.13') {
        try {
            $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
        } catch { }
    }
    foreach ($n in 'python', 'python3') {
        try {
            $ok = & $n -c "import sys; print(int((3,11) <= sys.version_info[:2] < (3,14)))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ok -eq '1') { return (& $n -c "import sys; print(sys.executable)").Trim() }
        } catch { }
    }
    return $null
}

function Run($exe, [string[]]$argList) {
    & $exe @argList
    if ($LASTEXITCODE -ne 0) { Fail "comando falhou: $exe $($argList -join ' ')" }
}

Write-Host "== Ragnarok: instalação ==" -ForegroundColor Cyan

$free = (Get-PSDrive -Name ((Get-Location).Drive.Name)).Free
if ($free -gt 0 -and $free -lt 3GB) { Write-Host ("AVISO: só {0:N1} GB livres neste disco; recomendo pelo menos 3 GB." -f ($free / 1GB)) -ForegroundColor Yellow }

$py = Get-PythonExe
if (-not $py) {
    Fail "Python 3.11, 3.12 ou 3.13 (64 bits) não encontrado. Instale com:  winget install -e --id Python.Python.3.12  e rode este script de novo."
}
Write-Host "Python: $py"
Run $py @('-c', 'import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)')   # exige Python de 64 bits

# Aviso (não bloqueia): o onnxruntime precisa do runtime Visual C++ 2015-2022 x64
$vc = Test-Path 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
if (-not $vc) { Write-Host "AVISO: runtime Visual C++ x64 não detectado. Se der erro de DLL, instale:  winget install -e --id Microsoft.VCRedist.2015+.x64" -ForegroundColor Yellow }

if (-not (Test-Path '.venv\Scripts\python.exe')) { Run $py @('-m', 'venv', '.venv') }
$vpy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Run $vpy @('-m', 'pip', 'install', '--upgrade', 'pip', '-q')
Run $vpy @('-m', 'pip', 'install', '-r', 'requirements.txt')
Run $vpy @('-m', 'ragnarok', 'models')
if (-not $SkipTest) { Run $vpy @('-m', 'ragnarok', 'doctor') }

Write-Host ""
Write-Host "Pronto! Para abrir:  .\ragnarok.bat     (ou  .\run.ps1)" -ForegroundColor Green
Write-Host "Exemplo:  .\ragnarok.bat say ""Olá, mundo"" --voice sabio-pt --speed 0.85 --out ola.wav"
