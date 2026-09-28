$ErrorActionPreference = "Stop"

$repo = "ehk2509/ai-coding-context-optimizer"
$version = if ($env:ACCO_VERSION) { $env:ACCO_VERSION } else { "latest" }
$installDir = if ($env:ACCO_INSTALL_DIR) {
    $env:ACCO_INSTALL_DIR
} else {
    Join-Path $env:LOCALAPPDATA "ACCO\bin"
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "ACCO standalone Windows builds currently require 64-bit Windows."
}
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$assetArch = switch ($architecture) {
    "X64" { "x86_64" }
    "Arm64" { "arm64" }
    default {
        throw "Unsupported Windows architecture $architecture. Use 'uv tool install acco' for this machine."
    }
}

$base = if ($version -eq "latest") {
    "https://github.com/$repo/releases/latest/download"
} else {
    "https://github.com/$repo/releases/download/$version"
}
$asset = "acco-windows-$assetArch.exe"

$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("acco-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $temp | Out-Null
try {
    $binary = Join-Path $temp "acco.exe"
    $checksum = Join-Path $temp "$asset.sha256"
    Invoke-WebRequest -Uri "$base/$asset" -OutFile $binary
    Invoke-WebRequest -Uri "$base/$asset.sha256" -OutFile $checksum

    $expected = ((Get-Content $checksum -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 $binary).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw "Checksum verification failed."
    }

    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    $target = Join-Path $installDir "acco.exe"
    Copy-Item -Force $binary $target

    & $target --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Installed ACCO executable failed its smoke test."
    }

    $normalizedInstall = [IO.Path]::GetFullPath($installDir).TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $userEntries = @()
    if ($userPath) {
        $userEntries = $userPath -split ';' | Where-Object { $_ }
    }
    $alreadyOnUserPath = $false
    foreach ($entry in $userEntries) {
        try {
            if ([IO.Path]::GetFullPath($entry).TrimEnd('\') -ieq $normalizedInstall) {
                $alreadyOnUserPath = $true
                break
            }
        } catch {
            if ($entry.TrimEnd('\') -ieq $normalizedInstall) {
                $alreadyOnUserPath = $true
                break
            }
        }
    }
    if (-not $alreadyOnUserPath) {
        $newUserPath = if ($userPath) { "$userPath;$installDir" } else { $installDir }
        [Environment]::SetEnvironmentVariable("Path", $newUserPath, "User")
    }

    $currentEntries = $env:Path -split ';'
    if (-not ($currentEntries | Where-Object { $_.TrimEnd('\') -ieq $normalizedInstall })) {
        $env:Path = "$installDir;$env:Path"
    }

    Write-Host "Installed ACCO to $target"
    if (-not $alreadyOnUserPath) {
        Write-Host "Added $installDir to your user PATH."
        Write-Host "New terminals will pick up the PATH change automatically."
    }
    Write-Host "Next: cd <project>; acco setup"
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $temp
}
