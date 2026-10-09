<#
.SYNOPSIS
    Atalhos de operação do OpsPilot para Windows PowerShell.

.DESCRIPTION
    Equivalente ao Makefile. Execute na raiz do repositório:

        ./scripts/ops.ps1 up
        ./scripts/ops.ps1 test-backend
        ./scripts/ops.ps1 help

.PARAMETER Command
    Comando a executar (use "help" para a lista completa).
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$Venv = Join-Path $BackendDir '.venv\Scripts'

function Invoke-Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "Falha em: $Title (codigo $LASTEXITCODE)"
    }
}

function Get-Python {
    $venvPython = Join-Path $Venv 'python.exe'
    if (Test-Path $venvPython) { return $venvPython }
    return 'python'
}

function Show-Help {
    Write-Host 'OpsPilot - comandos disponiveis' -ForegroundColor Green
    @(
        @{ c = 'up';             d = 'Sobe postgres + backend + frontend (docker compose up --build -d)' },
        @{ c = 'up-automation';  d = 'Sobe o ambiente incluindo o n8n (profile opcional)' },
        @{ c = 'down';           d = 'Derruba os servicos' },
        @{ c = 'stop';           d = 'Para os servicos sem remover containers' },
        @{ c = 'ps';             d = 'Estado dos servicos' },
        @{ c = 'logs';           d = 'Logs de todos os servicos' },
        @{ c = 'logs-backend';   d = 'Logs do backend' },
        @{ c = 'health';         d = 'Consulta http://localhost:8000/health' },
        @{ c = 'migrate';        d = 'Aplica migrations no container do backend' },
        @{ c = 'seed';           d = 'Executa o seed idempotente' },
        @{ c = 'seed-reset';     d = 'Limpa a organizacao demo e semeia novamente' },
        @{ c = 'samples';        d = 'Gera as planilhas sinteticas em data/samples' },
        @{ c = 'db-reset';       d = 'Destroi o volume do postgres e recria o banco' },
        @{ c = 'install';        d = 'Instala dependencias de backend e frontend' },
        @{ c = 'test';           d = 'Executa todos os testes' },
        @{ c = 'test-backend';   d = 'pytest' },
        @{ c = 'test-frontend';  d = 'vitest' },
        @{ c = 'e2e';            d = 'Playwright contra o ambiente em execucao' },
        @{ c = 'lint';           d = 'Ruff + MyPy + ESLint + tsc' },
        @{ c = 'format';         d = 'Formata o backend com ruff' },
        @{ c = 'build';          d = 'docker compose build' },
        @{ c = 'build-frontend'; d = 'Build de producao do frontend' },
        @{ c = 'dev-backend';    d = 'Backend local com SQLite e reload' },
        @{ c = 'dev-frontend';   d = 'Frontend local com Vite' },
        @{ c = 'smoke';          d = 'Checagem rapida pos-subida' }
    ) | ForEach-Object { Write-Host ("  {0,-16} {1}" -f $_.c, $_.d) }
}

switch ($Command.ToLowerInvariant()) {
    'help' { Show-Help }

    'up' {
        Invoke-Step 'docker compose up --build -d' { docker compose up --build -d }
        Write-Host 'Backend:  http://localhost:8000/docs' -ForegroundColor Green
        Write-Host 'Frontend: http://localhost:5173' -ForegroundColor Green
    }
    'up-automation' {
        Invoke-Step 'docker compose --profile automation up --build -d' {
            docker compose --profile automation up --build -d
        }
        Write-Host 'n8n: http://localhost:5678' -ForegroundColor Green
    }
    'down'  { Invoke-Step 'docker compose down' { docker compose down --remove-orphans } }
    'stop'  { Invoke-Step 'docker compose stop' { docker compose stop } }
    'ps'    { docker compose ps }
    'logs'  { docker compose logs -f --tail=100 }
    'logs-backend' { docker compose logs -f --tail=200 backend }
    'health' { Invoke-RestMethod -Uri 'http://localhost:8000/health' | ConvertTo-Json -Depth 5 }

    'migrate' { Invoke-Step 'alembic upgrade head' { docker compose exec backend alembic upgrade head } }
    'seed'    { Invoke-Step 'seed' { docker compose exec backend python scripts_seed.py } }
    'seed-reset' {
        Invoke-Step 'seed --reset' { docker compose exec backend python scripts_seed.py --reset }
    }
    'samples' {
        Invoke-Step 'gerar amostras' {
            & (Get-Python) (Join-Path $RepoRoot 'scripts\generate_sample_data.py')
        }
    }
    'db-reset' {
        Invoke-Step 'docker compose down -v' { docker compose down -v }
        Invoke-Step 'subindo o banco' { docker compose up -d db }
        Write-Host 'Aguardando o postgres...' -ForegroundColor Yellow
        for ($i = 0; $i -lt 60; $i++) {
            docker compose exec -T db pg_isready -U opspilot -d opspilot *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 1
        }
        Invoke-Step 'subindo o backend' { docker compose up -d --build backend }
        Write-Host 'Banco recriado. Migrations e seed rodam no entrypoint do backend.' -ForegroundColor Green
    }

    'install' {
        Invoke-Step 'venv do backend' {
            Push-Location $BackendDir
            python -m venv .venv
            & (Join-Path $Venv 'python.exe') -m pip install --upgrade pip
            & (Join-Path $Venv 'pip.exe') install -e ".[dev]"
            Pop-Location
        }
        Invoke-Step 'npm install' { Push-Location $FrontendDir; npm install; Pop-Location }
    }

    'test' {
        & $PSCommandPath 'test-backend'
        & $PSCommandPath 'test-frontend'
    }
    'test-backend' {
        Invoke-Step 'pytest' {
            Push-Location $BackendDir
            & (Get-Python) -m pytest -q @Rest
            Pop-Location
        }
    }
    'test-frontend' {
        Invoke-Step 'vitest' { Push-Location $FrontendDir; npm run test -- --run; Pop-Location }
    }
    'e2e' {
        Invoke-Step 'playwright' { Push-Location $FrontendDir; npm run test:e2e; Pop-Location }
    }

    'lint' {
        Invoke-Step 'ruff check' {
            Push-Location $BackendDir; & (Get-Python) -m ruff check .; Pop-Location
        }
        Invoke-Step 'ruff format --check' {
            Push-Location $BackendDir; & (Get-Python) -m ruff format --check .; Pop-Location
        }
        Invoke-Step 'mypy' { Push-Location $BackendDir; & (Get-Python) -m mypy; Pop-Location }
        Invoke-Step 'eslint' { Push-Location $FrontendDir; npm run lint; Pop-Location }
        Invoke-Step 'tsc' { Push-Location $FrontendDir; npm run typecheck; Pop-Location }
    }
    'format' {
        Invoke-Step 'ruff format' {
            Push-Location $BackendDir; & (Get-Python) -m ruff format .; Pop-Location
        }
    }
    'build' { Invoke-Step 'docker compose build' { docker compose build } }
    'build-frontend' {
        Invoke-Step 'npm run build' { Push-Location $FrontendDir; npm run build; Pop-Location }
    }

    'dev-backend' {
        Push-Location $BackendDir
        $env:OPSPILOT_DATABASE_URL = 'sqlite+aiosqlite:///./var/dev.db'
        & (Get-Python) -m uvicorn app.main:app --reload
        Pop-Location
    }
    'dev-frontend' { Push-Location $FrontendDir; npm run dev; Pop-Location }
    'smoke' {
        Invoke-Step 'smoke test' {
            & (Get-Python) (Join-Path $RepoRoot 'scripts\smoke_test.py')
        }
    }

    default {
        Write-Host "Comando desconhecido: $Command" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
