# Corrida de la noche: malla grande (+ estela) -> barrido de CFD con los dos modelos -> comparacion y calibracion.
#
# Uso (PowerShell, desde la raiz del repo):
#     .\herramientas\correr_noche.ps1 -Limite 08:30
#     .\herramientas\correr_noche.ps1 -Limite 08:30 -SinEstela              # sin refinamiento de estela
#     .\herramientas\correr_noche.ps1 -Plan "transicion:4;sst:4" -Limite 06:00
#
# Antes de irte: Configuracion > Sistema > Energia > suspension y apagado de pantalla en "Nunca", equipo enchufado.
# Cada paso escribe su log en resultados\cfd_run\log_noche_*.txt. Se puede relanzar: lo que ya esta hecho se saltea
# (la malla si ya existe, los casos que ya estan en resultados.csv).
param(
    [string]$Limite = "08:30",
    [string]$Plan = "transicion:0,4;sst:4;transicion:1.21,8;sst:0,1.21,8",
    [string]$Etiqueta = "noche_grande",
    [switch]$SinEstela
)
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$pyf = "C:\Users\felip\venv_pyfluent\Scripts\python.exe"      # PyFluent 0.27 (Fluent 24.1)
$run = Join-Path $raiz "resultados\cfd_run"
$malla = Join-Path $run "malla_grande.msh.h5"
$mallaV5 = Join-Path $run "malla_v5.msh.h5"
New-Item -ItemType Directory -Force -Path $run | Out-Null

function Celdas($etq) {
    $j = Join-Path $run ("malla_{0}.json" -f $etq)
    if (Test-Path $j) { return (Get-Content $j -Raw | ConvertFrom-Json).celdas } else { return $null }
}
function Fluent-Huerfanos {
    # avisa de fluent.exe vivos (ocupan licencia y nucleos); NO los mata: cerrar a mano por PID
    $p = Get-CimInstance Win32_Process | Where-Object Name -eq "fluent.exe"
    if ($p) { Write-Host ("AVISO: hay {0} fluent.exe vivo(s): {1}" -f @($p).Count, ((@($p) | ForEach-Object ProcessId) -join ", ")) }
}

# 1) Malla grande -------------------------------------------------------------------------------------------
if (-not (Test-Path $malla)) {
    if (-not $SinEstela) {
        Write-Host ">> malla grande CON estela"
        & $pyf -u herramientas\mallar_fluent.py --step encl_grande.step --etiqueta grande --tam-max 1500 `
            --estela zona_estela.step --tam-estela 200 *> (Join-Path $run "log_noche_malla.txt")
        $n = Celdas "grande"
        if (-not (Test-Path $malla) -or ($n -and $n -gt 7000000)) {
            Write-Host ("   la malla con estela fallo o es demasiado grande ({0} celdas): reintento sin estela" -f $n)
            Remove-Item $malla -ErrorAction SilentlyContinue
            $SinEstela = $true
        }
    }
    if ($SinEstela -and -not (Test-Path $malla)) {
        Write-Host ">> malla grande SIN estela"
        & $pyf -u herramientas\mallar_fluent.py --step encl_grande.step --etiqueta grande --tam-max 1500 `
            *> (Join-Path $run "log_noche_malla_sin_estela.txt")
    }
    Fluent-Huerfanos
}
$mallaUsar = $malla
if (-not (Test-Path $malla)) {
    Write-Host "!! no hay malla grande: uso malla_v5 (recinto chico, tapas como velocity-inlet). Los resultados NO son del recinto nuevo."
    $mallaUsar = $mallaV5
    $Etiqueta = "noche_v5"
} else {
    Write-Host (">> malla grande lista: {0} celdas" -f (Celdas "grande"))
}

# 2) Barrido de CFD -----------------------------------------------------------------------------------------
Write-Host (">> CFD: plan '{0}' hasta {1}" -f $Plan, $Limite)
& $pyf -u herramientas\correr_cfd_fluent.py --malla $mallaUsar --plan $Plan --limite $Limite --etiqueta $Etiqueta `
    *> (Join-Path $run ("log_noche_cfd_{0}.txt" -f $Etiqueta))
Fluent-Huerfanos

# 3) Comparacion y calibracion contra AeroBuildup (Python del proyecto) -------------------------------------------
Write-Host ">> comparacion y calibracion"
$py = if (Test-Path (Join-Path $raiz ".venv\Scripts\python.exe")) { Join-Path $raiz ".venv\Scripts\python.exe" } else { "python" }
& $py herramientas\calibrar_cfd_aerobuildup.py *> (Join-Path $run "log_noche_calibracion.txt")
Write-Host "Listo. Resultados: resultados\cfd_run\noche\$Etiqueta\resultados.csv | resultados\calibracion_cfd.png"
