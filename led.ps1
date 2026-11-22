# Run from any directory. Prefer the project venv, then the existing portable
# validation interpreter. No activation, PATH changes, or package downloads.
$ErrorActionPreference = 'Stop'
$dependencies = '-'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')) {
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
} elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.analysis/cpython/python.exe')) {
    $python = Join-Path $PSScriptRoot '.analysis/cpython/python.exe'
    $dependencies = Join-Path $PSScriptRoot '.analysis/windows'
} else {
    $python = (Get-Command python -ErrorAction Stop).Source
}
& $python -c 'import sys; root, deps = sys.argv[1:3]; del sys.argv[1:3]; sys.path.insert(0, root); sys.path.extend([deps] if deps != "-" else []); from magical_led.cli import main; sys.exit(main())' $PSScriptRoot $dependencies @args
exit $LASTEXITCODE
