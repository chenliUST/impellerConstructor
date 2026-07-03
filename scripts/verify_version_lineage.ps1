param(
    [switch]$SkipGitTags,
    [switch]$KeepWorktrees
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VersionCases = @(
    @{
        Version = "v0_2"
        DslVersion = "0.2"
        Tag = "impeller-dsl-v0.2"
        Presets = @("radial_open_reference", "radial_closed_reference")
    },
    @{
        Version = "v0_3"
        DslVersion = "0.3"
        Tag = "impeller-dsl-v0.3"
        Presets = @("radial_open_reference_v0_3", "radial_closed_reference_v0_3")
    },
    @{
        Version = "v0_4"
        DslVersion = "0.4"
        Tag = "impeller-dsl-v0.4"
        Presets = @("radial_open_reference_v0_4", "radial_closed_reference_v0_4")
    },
    @{
        Version = "v0_5"
        DslVersion = "0.5"
        Tag = $null
        Presets = @("radial_open_reference_v0_5", "radial_closed_reference_v0_5")
    },
    @{
        Version = "v0_6"
        DslVersion = "0.6"
        Tag = $null
        Presets = @("radial_open_reference_v0_6", "radial_closed_reference_v0_6")
    },
    @{
        Version = "v0_7"
        DslVersion = "0.7"
        Tag = $null
        Presets = @("radial_open_reference_v0_7", "radial_closed_reference_v0_7")
    }
)

function Invoke-LineageSmoke {
    param(
        [string]$RepositoryPath,
        [string]$ExpectedDslVersion,
        [string[]]$PresetIds
    )

    Push-Location $RepositoryPath
    try {
        $env:PYTHONPATH = "src"
        $env:VERSION_SMOKE_EXPECTED_DSL = $ExpectedDslVersion
        $env:VERSION_SMOKE_PRESETS = ($PresetIds -join ";")

        @'
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from part_rule_synthesis.service import RuleSynthesisService

expected_dsl = os.environ["VERSION_SMOKE_EXPECTED_DSL"]
preset_ids = [item for item in os.environ["VERSION_SMOKE_PRESETS"].split(";") if item]

with TemporaryDirectory() as temp_dir:
    service = RuleSynthesisService(Path(temp_dir) / "runs")
    for preset_id in preset_ids:
        engine = service.synthesize("impeller", preset_id=preset_id)
        run = service.instantiate(engine.engine_id, {})
        manifest = run.manifest
        actual_dsl = str(manifest.get("dsl_version"))
        if actual_dsl != expected_dsl:
            raise SystemExit(f"{preset_id}: expected DSL {expected_dsl}, got {actual_dsl}")
        if manifest.get("preset_id") != preset_id:
            raise SystemExit(f"{preset_id}: manifest preset mismatch")
        if manifest.get("geometry_validity", {}).get("status") != "PASS":
            raise SystemExit(f"{preset_id}: geometry validity did not pass")

print(f"lineage smoke passed: DSL {expected_dsl} presets={','.join(preset_ids)}")
'@ | python -
        if ($LASTEXITCODE -ne 0) {
            throw "lineage smoke failed in $RepositoryPath"
        }
    }
    finally {
        Pop-Location
    }
}

Write-Host "Checking current versioned resource folders..."
foreach ($case in $VersionCases) {
    Invoke-LineageSmoke -RepositoryPath $RepoRoot -ExpectedDslVersion $case.DslVersion -PresetIds $case.Presets
}

if ($SkipGitTags) {
    Write-Host "Skipping git tag worktree checks."
    exit 0
}

$isShallow = (git rev-parse --is-shallow-repository).Trim()
if ($isShallow -eq "true") {
    throw "Repository is shallow. Run: git fetch --unshallow --tags origin"
}

$worktreeRoot = Join-Path $RepoRoot ".worktrees\version-lineage"
New-Item -ItemType Directory -Force -Path $worktreeRoot | Out-Null

Write-Host "Checking historical git tags through temporary worktrees..."
foreach ($case in $VersionCases) {
    $tag = $case.Tag
    if (-not $tag) {
        continue
    }
    git rev-parse --verify --quiet "refs/tags/$tag" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Missing local tag: $tag"
    }

    $worktreePath = Join-Path $worktreeRoot "$tag-$PID"
    git -c core.longpaths=true worktree add --detach $worktreePath $tag | Out-Null
    try {
        Invoke-LineageSmoke -RepositoryPath $worktreePath -ExpectedDslVersion $case.DslVersion -PresetIds $case.Presets
    }
    finally {
        if (-not $KeepWorktrees) {
            git worktree remove --force $worktreePath | Out-Null
        }
    }
}

if (-not $KeepWorktrees) {
    git worktree prune | Out-Null
}

Write-Host "Version lineage verification passed."
