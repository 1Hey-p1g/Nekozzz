[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Prepare','Publish-Draft','Publish-Final')][string]$Action,
    [Parameter(Mandatory)][string]$Config,
    [string]$RepoPath,
    [string]$PythonExe,
    [string]$ApprovedManifestSha256,
    [switch]$ConfirmDraft,
    [switch]$ConfirmPublicRelease
)
# This script never initializes a repository, updates main, forces a push, or
# deletes/replaces remote assets. Every remote mutation needs a separate gate.
Set-StrictMode -Version Latest
if (-not $RepoPath) { $RepoPath = Split-Path $PSScriptRoot -Parent }
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$previousOutputEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$configPath = (Resolve-Path -LiteralPath $Config).Path
$configuration = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$configRoot = Split-Path $configPath -Parent
$assetRoot = [IO.Path]::GetFullPath((Join-Path $configRoot $configuration.asset_root))
$planPath = Join-Path $assetRoot 'PUBLISH_MANIFEST.json'
$statePath = Join-Path $assetRoot 'PUBLISH_STATE.json'
$verificationPath = Join-Path $assetRoot 'LOCAL_VERIFICATION.json'
$repo = $configuration.repo
$tag = $configuration.tag
$state = @{}
if (Test-Path -LiteralPath $statePath) {
    $loadedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $loadedState.PSObject.Properties) { $state[$property.Name] = $property.Value }
}
function Save-Json([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 30), $utf8)
}
function Save-State([string]$Phase) {
    $state['phase'] = $Phase
    $state['updated_utc'] = [DateTime]::UtcNow.ToString('o')
    Save-Json $statePath $state
}
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Native([string]$Exe, [string[]]$Arguments, [switch]$AllowFailure) {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $executable = (Get-Command $Exe -CommandType Application -ErrorAction Stop).Source
        $lines = @(& $executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    $answer = [pscustomobject]@{ code = $code; text = ($lines -join "`n") }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "$Exe failed (exit $code): $($answer.text)"
    }
    $answer
}
function Git([string[]]$Arguments) { (Native 'git' (@('-C',$RepoPath) + $Arguments)).text }
function Gh([string[]]$Arguments) { (Native 'gh' $Arguments).text }
function Verify-Local([switch]$WithGit, [string]$Commit) {
    $outputFile = $verificationPath
    if ($WithGit) { $outputFile = Join-Path $assetRoot 'GIT_VERIFICATION.json' }
    $arguments = @('-B',(Join-Path $PSScriptRoot 'verify_release.py'),'--config',$configPath,'--output',$outputFile)
    if ($WithGit) { $arguments += @('--repo-path',$RepoPath) }
    if ($Commit) { $arguments += @('--commit',$Commit) }
    $null = Native $PythonExe $arguments
    $result = Get-Content -LiteralPath $outputFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $result.valid) { throw 'Local/source verification failed' }
    $result
}
function Remote-Tags([string]$Name) {
    # Read-only. Empty successful output means absent; a network/auth failure throws.
    Git @('ls-remote','--tags','origin',"refs/tags/$Name","refs/tags/$Name^{}")
}
function Assert-Baseline {
    $remote = Remote-Tags $configuration.baseline_tag
    $local = Git @('rev-parse',"$($configuration.baseline_tag)^{object}")
    $ref = "refs/tags/$($configuration.baseline_tag)"
    if (-not @($remote -split "`n" | Where-Object { $_ -eq "$local`t$ref" }).Count) {
        throw 'Local baseline tag does not match origin; fetch/review it manually'
    }
}
function Assert-Github {
    $null = Gh @('auth','status','--hostname','github.com')
    $information = Gh @('api',"repos/$repo") | ConvertFrom-Json
    if ($information.full_name -ine $repo -or $information.private) {
        throw 'Expected public repository required for public source access'
    }
    if (-not $information.permissions.push) { throw 'GitHub account has no repository push permission' }
}
function Get-Release {
    Gh @('release','view',$tag,'--repo',$repo,'--json','tagName,isDraft,isPrerelease,name,url,assets,targetCommitish,body') | ConvertFrom-Json
}
function Find-Release {
    $result = Native 'gh' @('release','view',$tag,'--repo',$repo,'--json','tagName,isDraft,isPrerelease,name,url,assets,targetCommitish,body') -AllowFailure
    if ($result.code -eq 0) { return ($result.text | ConvertFrom-Json) }
    if ($result.text -match 'release not found') { return $null }
    throw "Cannot determine whether release exists: $($result.text)"
}
function Notes-Body([string]$ManifestHash) {
    $notesAsset = @($plan.assets | Where-Object { $_.role -eq 'notes' })[0]
    $notes = [IO.File]::ReadAllText((Join-Path $assetRoot $notesAsset.name)).Replace("`r`n","`n").TrimEnd()
    $notes + "`n`n<!-- Release plan SHA256: $ManifestHash -->"
}
function Assert-OwnedRelease($Release, [string]$ManifestHash) {
    if ($Release.tagName -ne $tag -or $Release.name -ne $tag -or $Release.isPrerelease) { throw 'Unexpected release identity' }
    if ($Release.body.Replace("`r`n","`n").TrimEnd() -cne (Notes-Body $ManifestHash).TrimEnd()) { throw 'Release body does not belong to approved plan' }
    if ($Release.targetCommitish -ne $state['commit']) { throw 'Release commit differs from verified source commit' }
}
function Assert-RemoteCommit {
    $raw = Remote-Tags $tag
    $peeled = @($raw -split "`n" | Where-Object { $_ -match '\^\{\}$' })
    if ($peeled.Count -ne 1 -or ($peeled[0] -split "`t")[0] -ne $state['commit']) { throw 'Remote tag does not peel to verified commit' }
    $direct = @($raw -split "`n" | Where-Object { $_ -notmatch '\^\{\}$' -and $_ })
    if ($direct.Count -ne 1 -or ($direct[0] -split "`t")[0] -ne $state['tag_object']) { throw 'Remote annotated tag object mismatch' }
}
function Download-Assets($Release, [switch]$Anonymous) {
    $expected = @($plan.assets.name | Sort-Object)
    $actual = @($Release.assets.name | Sort-Object)
    if (@(Compare-Object $expected $actual).Count) { throw 'Missing, extra, or duplicate remote release assets' }
    if ($Release.assets.Count -ne $expected.Count) { throw 'Duplicate remote assets' }
    $directory = Join-Path $assetRoot ('verification-downloads/' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $directory
    foreach ($asset in $plan.assets) {
        $remoteAsset = @($Release.assets | Where-Object { $_.name -ceq $asset.name })[0]
        if ($remoteAsset.size -ne $asset.bytes) { throw "Remote asset size mismatch: $($asset.name)" }
        $file = Join-Path $directory $asset.name
        if ($Anonymous) {
            $url = "https://github.com/$repo/releases/download/$tag/$($asset.name)"
            # Intentionally unauthenticated; never read/save a token.
            Invoke-WebRequest -Uri $url -OutFile $file -UseBasicParsing
        } else {
            $null = Gh @('release','download',$tag,'--repo',$repo,'--pattern',$asset.name,'--dir',$directory)
        }
        if ((Hash $file) -ne $asset.sha256) { throw "Downloaded SHA256 mismatch: $($asset.name)" }
    }
    $directory
}
function Check-Approval([string]$ManifestHash) {
    if (-not $ApprovedManifestSha256 -or $ApprovedManifestSha256.ToLowerInvariant() -ne $ManifestHash) {
        throw 'Pass the exact reviewed manifest SHA256; no implicit approval'
    }
    if ((Hash $configPath) -ne $plan.config_sha256) { throw 'Configuration changed after Prepare' }
    foreach ($asset in $plan.assets) {
        if ((Hash (Join-Path $assetRoot $asset.name)) -ne $asset.sha256) { throw 'Approved asset changed' }
    }
    foreach ($control in $plan.control_files) {
        if ((Hash $control.path) -ne $control.sha256) { throw 'Publishing control script changed after Prepare' }
    }
}
function Assert-WorkingHashes($GitInfo) {
    $expected = @($plan.git.approved_worktree_hashes.PSObject.Properties)
    $actual = @($GitInfo.approved_worktree_hashes.PSObject.Properties)
    if ($expected.Count -ne $actual.Count) { throw 'Approved working file set changed' }
    foreach ($property in $expected) {
        $value = $GitInfo.approved_worktree_hashes.PSObject.Properties[$property.Name]
        if (-not $value -or $value.Value -cne $property.Value) { throw "Approved working file changed: $($property.Name)" }
    }
}

# Hold a lock while operating. Failure keeps the state and downloads for review.
$lockPath = Join-Path $assetRoot 'PUBLISH.lock'
$lock = $null
try {
    $lock = [IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    if (-not $PythonExe) {
        $candidate = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv/Scripts/python.exe'
        if (Test-Path -LiteralPath $candidate) { $PythonExe = $candidate }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { $PythonExe = (Get-Command python).Source }
        else { throw 'Python 3.11+ required for read-only ZIP/source verification' }
    }
    if ($Action -eq 'Prepare') {
        if ($state.ContainsKey('commit')) { throw 'Existing publication state: resume it; do not replace its approved plan' }
        $blockers = New-Object System.Collections.Generic.List[string]
        $local = $null
        try { $local = Verify-Local } catch { $blockers.Add($_.Exception.Message) }
        $gitInfo = $null
        if (-not (Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) { $blockers.Add('Git is not installed') }
        else {
            try { $gitInfo = (Verify-Local -WithGit).git } catch { $blockers.Add($_.Exception.Message) }
        }
        $githubReady = $false
        if (-not (Get-Command gh -CommandType Application -ErrorAction SilentlyContinue)) { $blockers.Add('GitHub CLI (gh) is not installed; install and log in manually') }
        else {
            try { Assert-Github; $githubReady = $true } catch { $blockers.Add($_.Exception.Message) }
        }
        if ($gitInfo -and $githubReady) {
            try {
                Assert-Baseline
                if (Remote-Tags $tag) { throw 'Target tag already exists; never overwrite/adopt it automatically' }
                $releases = Gh @('release','list','--repo',$repo,'--limit','1000','--json','tagName') | ConvertFrom-Json
                if (@($releases | Where-Object { $_.tagName -eq $tag }).Count) { throw 'Target release already exists' }
            } catch { $blockers.Add($_.Exception.Message) }
        }
        $plan = [ordered]@{
            schema = 1; action = 'Prepare'; repo = $repo; tag = $tag; repo_path = [IO.Path]::GetFullPath($RepoPath)
            config_sha256 = Hash $configPath; status = 'BLOCKED'; blockers = @($blockers.ToArray())
            generated_utc = [DateTime]::UtcNow.ToString('o'); local = $local; git = $gitInfo; assets = @()
            control_files = @(@{path=$PSCommandPath;sha256=Hash $PSCommandPath},@{path=(Join-Path $PSScriptRoot 'verify_release.py');sha256=Hash (Join-Path $PSScriptRoot 'verify_release.py')})
            planned_operations = @('Commit only listed approved files if needed','Verify resulting commit against RC source','Create annotated tag; push only that tag, never main','Create Draft Release using --verify-tag --draft','Upload missing attachments without clobber','Download and hash-check every attachment','Stop before public release')
        }
        if ($local) { $plan.assets = @($local.assets) }
        if (-not $blockers.Count) { $plan.status = 'PREPARED — EXPLICIT DRAFT APPROVAL REQUIRED' }
        Save-Json $planPath $plan
        Write-Host "Prepare: $($plan.status)"
        Write-Host "Manifest: $planPath"
        Write-Host "Manifest SHA256: $(Hash $planPath)"
        foreach ($reason in $blockers) { Write-Host "BLOCKER: $reason" }
        if ($blockers.Count) { exit 2 }
        exit 0
    }
    if (-not (Test-Path -LiteralPath $planPath)) { throw 'Run Prepare first' }
    $plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($plan.status -ne 'PREPARED — EXPLICIT DRAFT APPROVAL REQUIRED') { throw 'Prepare is blocked' }
    if ($plan.repo_path -ine [IO.Path]::GetFullPath($RepoPath)) { throw 'RepoPath differs from approved plan' }
    $manifestHash = Hash $planPath
    Check-Approval $manifestHash
    Assert-Github
    Assert-Baseline
    if ($state.Count -and ($state['manifest_sha256'] -ne $manifestHash -or $state['repo'] -ne $repo -or $state['tag'] -ne $tag)) { throw 'Publication state belongs to another plan' }
    if ($Action -eq 'Publish-Draft') {
        if (-not $ConfirmDraft) { throw 'Publish-Draft requires -ConfirmDraft after developer reviews exact operations' }
        if (-not $state.ContainsKey('commit')) {
            if (Remote-Tags $tag) { throw 'Remote target tag already exists' }
            $check = Verify-Local -WithGit
            if ($check.git.head -ne $plan.git.head -or $check.git.branch -ne $plan.git.branch) { throw 'Branch/HEAD changed after approval' }
            Assert-WorkingHashes $check.git
            if ((@($check.git.commit_files) -join "`n") -cne (@($plan.git.commit_files) -join "`n")) { throw 'Commit file set changed' }
            if ((Native 'git' @('-C',$RepoPath,'rev-parse','--verify',"refs/tags/$tag") -AllowFailure).code -eq 0) { throw 'Local target tag already exists' }
            $state['manifest_sha256']=$manifestHash; $state['repo']=$repo; $state['tag']=$tag
            Save-State 'STAGING_APPROVED_FILES'
            foreach ($file in $plan.git.commit_files) {
                if ($configuration.allow_ignored_source_files -contains $file) { $null = Git @('add','-f','--',$file) }
                else { $null = Git @('add','--',$file) }
            }
            if ($plan.git.commit_files.Count) { $null = Git @('commit','-m',"Release Nekozzz $tag (accepted RC source and release documents)") }
            $state['commit'] = Git @('rev-parse','HEAD')
            Save-State 'COMMITTED_LOCAL_SOURCE'
        }
        if ((Git @('rev-parse','HEAD')) -ne $state['commit']) { throw 'HEAD changed; inspect saved publication state' }
        $committed = Verify-Local -WithGit -Commit $state['commit']
        Assert-WorkingHashes $committed.git
        if ($committed.git.commit_files.Count) { throw 'Worktree not clean after release commit' }
        $localTag = Native 'git' @('-C',$RepoPath,'rev-parse','--verify',"refs/tags/$tag") -AllowFailure
        if (-not $state.ContainsKey('tag_object')) {
            if ($localTag.code -eq 0) { throw 'Local tag exists without script ownership; review manually' }
            $null = Git @('tag','-a',$tag,$state['commit'],'-m',"Nekozzz $tag; accepted release plan $manifestHash")
            $state['tag_object'] = Git @('rev-parse',"refs/tags/$tag")
            Save-State 'ANNOTATED_TAG_CREATED_LOCAL'
        }
        if ((Git @('cat-file','-t',"refs/tags/$tag")) -ne 'tag' -or (Git @('rev-parse',"refs/tags/$tag")) -ne $state['tag_object']) { throw 'Local annotated tag changed' }
        if (-not (Remote-Tags $tag)) {
            $null = Git @('push','--porcelain','origin',"refs/tags/${tag}:refs/tags/$tag")
        }
        Assert-RemoteCommit
        Save-State 'TAG_PUSHED — MAIN_UNCHANGED'
        $release = Find-Release
        if (-not $release) {
            $notesBody = Join-Path $assetRoot 'APPROVED_RELEASE_BODY.md'
            [IO.File]::WriteAllText($notesBody,(Notes-Body $manifestHash),$utf8)
            Save-State 'DRAFT_CREATE_IN_FLIGHT'
            $null = Gh @('release','create',$tag,'--repo',$repo,'--verify-tag','--draft','--target',$state['commit'],'--title',$tag,'--notes-file',$notesBody)
            $release = Get-Release
        }
        Assert-OwnedRelease $release $manifestHash
        if (-not $release.isDraft) { throw 'Existing release is public; Publish-Draft cannot change it' }
        $state['release_url'] = $release.url
        Save-State 'DRAFT_CREATED'
        foreach ($asset in $plan.assets) {
            $existing = @($release.assets | Where-Object { $_.name -ceq $asset.name })
            if ($existing.Count -gt 1) { throw 'Duplicate remote asset' }
            if ($existing.Count -eq 1) {
                $downloadRoot = Join-Path $assetRoot ('verification-downloads/' + [guid]::NewGuid().ToString('N'))
                $null = New-Item -ItemType Directory -Path $downloadRoot
                $null = Gh @('release','download',$tag,'--repo',$repo,'--pattern',$asset.name,'--dir',$downloadRoot)
                if ((Hash (Join-Path $downloadRoot $asset.name)) -ne $asset.sha256) { throw 'Existing asset differs; never overwrite it' }
            } else {
                $null = Gh @('release','upload',$tag,(Join-Path $assetRoot $asset.name),'--repo',$repo)
                Save-State ('UPLOADED ' + $asset.name)
            }
        }
        $release = Get-Release
        Assert-OwnedRelease $release $manifestHash
        if (-not $release.isDraft) { throw 'Release became public unexpectedly' }
        $state['authenticated_download_verification'] = Download-Assets $release
        Save-State 'DRAFT_VERIFIED — PUBLICATION_AWAITS_SEPARATE_CONFIRMATION'
        Write-Host "Draft verified: $($release.url)"
        Write-Host 'STOP. Publish-Final requires independent developer confirmation.'
        exit 0
    }
    if (-not $ConfirmPublicRelease) { throw 'Publish-Final requires independent -ConfirmPublicRelease approval' }
    if (-not $state.ContainsKey('commit') -or -not $state.ContainsKey('release_url')) { throw 'No owned verified Draft Release' }
    if ((Git @('rev-parse','HEAD')) -ne $state['commit']) { throw 'Local HEAD differs from release source commit' }
    $committed = Verify-Local -WithGit -Commit $state['commit']
    Assert-WorkingHashes $committed.git
    if ($committed.git.commit_files.Count) { throw 'Worktree changed after Draft' }
    Assert-RemoteCommit
    $release = Get-Release
    Assert-OwnedRelease $release $manifestHash
    $state['authenticated_download_verification'] = Download-Assets $release
    if ($release.isDraft) {
        Save-State 'PUBLICATION_EXPLICITLY_CONFIRMED'
        $null = Gh @('release','edit',$tag,'--repo',$repo,'--draft=false','--verify-tag')
    } elseif ($state['phase'] -notmatch 'PUBLIC|INTERRUPTED') {
        throw 'Release was published outside this script; review before adopting it'
    }
    Save-State 'PUBLIC — ANONYMOUS_DOWNLOAD_VERIFICATION_PENDING'
    $release = Get-Release
    Assert-OwnedRelease $release $manifestHash
    if ($release.isDraft) { throw 'Release still draft' }
    $state['anonymous_download_verification'] = Download-Assets $release -Anonymous
    Save-State 'PUBLIC_RELEASE_VERIFIED'
    Write-Host "Public release and unauthenticated downloads verified: $($release.url)"
    exit 0
} catch {
    if ($state.Count) { $state['error'] = $_.Exception.Message; Save-State 'INTERRUPTED — REVIEW STATE BEFORE RESUME' }
    Write-Error $_.Exception.Message
    exit 2
} finally {
    if ($lock) { $lock.Dispose() }
    [Console]::OutputEncoding = $previousOutputEncoding
}
