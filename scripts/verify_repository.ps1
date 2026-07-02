param(
    [ValidateSet("fast", "full")]
    [string]$Mode = "fast",
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$CheckGitTags
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($BackendOnly -and $FrontendOnly) {
    throw "BackendOnly and FrontendOnly cannot both be set."
}

function Invoke-BackendVerification {
    $env:PYTHONPATH = "src"
    python -m compileall -q src

    if ($Mode -eq "full") {
        python -m pytest tests -q
        return
    }

    python -m pytest `
        tests/test_impeller_surface_graph_export.py `
        tests/test_impeller_runtime_compiler.py `
        tests/test_impeller_v04_resources.py `
        tests/test_impeller_version_lineage.py `
        tests/test_impeller_design_space.py `
        tests/test_impeller_cfd_manifest.py `
        -q
}

function Invoke-FrontendVerification {
    Push-Location frontend
    try {
        npm.cmd test
        npm.cmd run build
    }
    finally {
        Pop-Location
    }
}

if (-not $FrontendOnly) {
    Invoke-BackendVerification
}

if (-not $BackendOnly) {
    Invoke-FrontendVerification
}

if ($CheckGitTags) {
    & (Join-Path $PSScriptRoot "verify_version_lineage.ps1")
}
