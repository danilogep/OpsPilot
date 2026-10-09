"""Rotas do módulo de importação."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import ContextDep, RequireAnalyst, RequireViewer, SessionDep
from app.core.config import settings
from app.core.errors import PayloadTooLargeError
from app.core.pagination import Page, PageParams, page_params
from app.db.models.enums import ImportStatus, RowStatus
from app.domains.imports import service
from app.domains.imports.schemas import (
    CanonicalFieldInfo,
    CommitResult,
    ImportJobDetail,
    ImportJobRead,
    ImportPreview,
    ImportReport,
    MappingUpdate,
    RowErrorRead,
    ValidationSummary,
    canonical_field_catalog,
)

router = APIRouter(prefix="/imports", tags=["Importações"])


def _detail(job: object, available_sheets: list[str] | None = None) -> ImportJobDetail:
    detail = ImportJobDetail.model_validate(job)
    if available_sheets is not None:
        detail.available_sheets = available_sheets
    return detail


@router.get(
    "/fields",
    response_model=list[CanonicalFieldInfo],
    summary="Campos do modelo canônico",
)
async def canonical_fields(_user: RequireViewer) -> list[CanonicalFieldInfo]:
    """Lista os campos canônicos, rótulos e sinônimos reconhecidos."""
    return canonical_field_catalog()


@router.post(
    "",
    response_model=ImportJobDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar arquivo (CSV, XLSX ou XLS)",
)
async def upload_import(
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
    file: Annotated[UploadFile, File(description="Planilha de clientes")],
) -> ImportJobDetail:
    """Recebe o arquivo, detecta as colunas e sugere o mapeamento."""
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise PayloadTooLargeError(f"Arquivo acima do limite de {settings.max_upload_mb} MB.")
    job = await service.create_import_job(
        session,
        organization_id=user.organization_id,
        actor=user,
        filename=file.filename,
        content_type=file.content_type,
        content=content,
        context=context,
    )
    return _detail(job, job.stats.get("available_sheets", []))


@router.get("", response_model=Page[ImportJobRead], summary="Listar importações")
async def list_imports(
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    import_status: Annotated[ImportStatus | None, Query(alias="status")] = None,
) -> Page[ImportJobRead]:
    """Lista as importações da organização."""
    jobs, total = await service.list_import_jobs(
        session, organization_id=user.organization_id, params=params, status=import_status
    )
    return Page.build([ImportJobRead.model_validate(job) for job in jobs], total, params)


@router.get("/{import_id}", response_model=ImportJobDetail, summary="Detalhe da importação")
async def get_import(
    import_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> ImportJobDetail:
    """Retorna a importação com o mapeamento atual."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    return _detail(job, job.stats.get("available_sheets", []))


@router.get(
    "/{import_id}/preview",
    response_model=ImportPreview,
    summary="Prévia com mapeamento e normalização",
)
async def preview_import(
    import_id: uuid.UUID,
    session: SessionDep,
    user: RequireViewer,
    limit: Annotated[int, Query(ge=1, le=50, description="Linhas na prévia")] = 10,
) -> ImportPreview:
    """Mostra as primeiras linhas já normalizadas e o que falta mapear."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    payload = await service.build_preview(session, job=job, limit=limit)
    payload["canonical_fields"] = canonical_field_catalog()
    return ImportPreview.model_validate(payload)


@router.put(
    "/{import_id}/mapping",
    response_model=ImportJobDetail,
    summary="Revisar o mapeamento de colunas",
)
async def update_mapping(
    import_id: uuid.UUID,
    payload: MappingUpdate,
    session: SessionDep,
    user: RequireAnalyst,
    context: ContextDep,
) -> ImportJobDetail:
    """Substitui o mapeamento sugerido pelo mapeamento revisado."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    job = await service.update_mapping(
        session,
        job=job,
        mappings=payload.mappings,
        sheet_name=payload.sheet_name,
        actor=user,
        context=context,
    )
    return _detail(job, job.stats.get("available_sheets", []))


@router.post(
    "/{import_id}/validate",
    response_model=ValidationSummary,
    summary="Validar todas as linhas",
)
async def validate_import(
    import_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> ValidationSummary:
    """Normaliza e valida o arquivo inteiro, registrando erros por linha."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    report = await service.validate_import(session, job=job, actor=user, context=context)
    return ValidationSummary(import_id=job.id, status=job.status, **report.as_dict())


@router.post(
    "/{import_id}/commit",
    response_model=CommitResult,
    summary="Confirmar a importação",
)
async def commit_import(
    import_id: uuid.UUID, session: SessionDep, user: RequireAnalyst, context: ContextDep
) -> CommitResult:
    """Grava os clientes válidos, criando planos e renovações necessárias."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    result = await service.commit_import(session, job=job, actor=user, context=context)
    return CommitResult.model_validate(result)


@router.get(
    "/{import_id}/errors",
    response_model=Page[RowErrorRead],
    summary="Linhas com erro ou duplicadas",
)
async def list_errors(
    import_id: uuid.UUID,
    session: SessionDep,
    user: RequireViewer,
    params: Annotated[PageParams, Depends(page_params)],
    row_status: Annotated[RowStatus | None, Query(alias="status")] = None,
) -> Page[RowErrorRead]:
    """Lista as linhas rejeitadas com a mensagem de cada campo."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    rows, total = await service.list_row_errors(
        session, job=job, params=params, only_status=row_status
    )
    return Page.build([RowErrorRead.model_validate(row) for row in rows], total, params)


@router.get("/{import_id}/report", response_model=ImportReport, summary="Relatório final")
async def import_report(
    import_id: uuid.UUID, session: SessionDep, user: RequireViewer
) -> ImportReport:
    """Consolida estatísticas, amostra de erros e recomendações."""
    job = await service.get_import_job(
        session, organization_id=user.organization_id, import_id=import_id
    )
    validation = None
    if isinstance(job.stats, dict) and job.stats.get("validation"):
        validation = ValidationSummary(
            import_id=job.id, status=job.status, **job.stats["validation"]
        )
    rows, _ = await service.list_row_errors(
        session, job=job, params=PageParams(page=1, page_size=10)
    )
    return ImportReport(
        job=_detail(job, job.stats.get("available_sheets", [])),
        validation=validation,
        sample_errors=[RowErrorRead.model_validate(row) for row in rows],
        recommendations=service.build_recommendations(job),
    )
