# Pecha os procesos do Anonimizador que corren dende un cartafol dado
# (o "runtime" do programa instalado: pythonw.exe, python.exe, tesseract.exe).
# Chámao o instalador/desinstalador antes de substituír ou borrar ficheiros.
param([Parameter(Mandatory = $true)][string]$Ruta)

$ruta = $Ruta.TrimEnd('\') + '\'
Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($ruta, [System.StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
