"""Serviço de importação: upload, mapeamento, validação e commit."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RequestContext
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnprocessableFileError, ValidationError
from app.core.files import SPREADSHEET_EXTENSIONS, store_upload, validate_upload
from app.core.logging import get_logger
from app.core.pagination import PageParams
from app.db.base import utcnow
from app.db.models import (
    Customer,
    CustomerStatus,
    ImportColumnMapping,
    ImportJob,
    ImportStatus,
    Plan,
    RawImportRow,
    Renewal,
    RenewalStatus,
    RowStatus,
    User,
)
from app.domains.audit import service as audit_service
from app.domains.imports.mapping import (
    CanonicalField,
    MappingSuggestion,
    missing_required_fields,
    suggest_mapping,
)
from app.domains.imports.pipeline import ValidationReport, validate_rows
from app.domains.imports.reader import FIRST_DATA_ROW, SheetData, read_spreadsheet
from app.domains.imports.schemas import ColumnMappingInput
from app.integrations.webhooks import dispatcher

logger = get_logger(__name__)

#: Quantidade de linhas devolvidas na prévia.
PREVIEW_ROWS = 10
#: Amostras de valores guardadas por coluna para ajudar na revisão.
SAMPLE_VALUES = 3
#: Subdiretório de uploads de importação.
UPLOAD_SUBDIR = "imports"


def _job_path(job: ImportJob) -> Path:
    return settings.upload_dir / UPLOAD_SUBDIR / job.stored_filename


async def _load_sheet(job: ImportJob, *, sheet_name: str | None = None) -> SheetData:
    """Relê o arquivo da importação a partir do disco."""
    path = _job_path(job)
    if not path.exists():
        raise UnprocessableFileError(
            "O arquivo desta importação não está mais disponível no servidor."
        )
    return read_spreadsheet(
        path.read_bytes(),
        extension=Path(job.original_filename).suffix.lower() or path.suffix.lower(),
        sheet_name=sheet_name or job.sheet_name,
    )


def _samples(sheet: SheetData, column: str) -> list[str]:
    values: list[str] = []
    for row in sheet.rows:
        raw = row.get(column)
        if raw is None:
            continue
        text = str(raw).strip()
        if text and text.lower() not in {"nan", "nat"} and text not in values:
            values.append(text[:80])
        if len(values) >= SAMPLE_VALUES:
            break
    return values


async def create_import_job(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor: User,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    context: RequestContext | None = None,
) -> ImportJob:
    """Recebe o arquivo, detecta colunas e sugere o mapeamento inicial."""
    safe_name, extension, effective_type = validate_upload(
        filename=filename,
        content_type=content_type,
        content=content,
        allowed=SPREADSHEET_EXTENSIONS,
    )
    sheet = read_spreadsheet(content, extension=extension)
    if not sheet.headers:
        raise UnprocessableFileError("Não foi possível identificar as colunas do arquivo.")

    stored = store_upload(
        content=content,
        safe_name=safe_name,
        extension=extension,
        content_type=effective_type,
        subdirectory=UPLOAD_SUBDIR,
    )
    job = ImportJob(
        organization_id=organization_id,
        created_by_id=actor.id,
        original_filename=safe_name,
        stored_filename=stored.stored_name,
        content_type=effective_type,
        size_bytes=stored.size_bytes,
        sheet_name=sheet.active_sheet,
        status=ImportStatus.UPLOADED,
        detected_columns=sheet.headers,
        total_rows=sheet.total_rows,
        stats={
            "available_sheets": sheet.sheet_names,
            "delimiter": sheet.delimiter,
            "encoding": sheet.encoding,
            "truncated": sheet.truncated,
        },
    )
    session.add(job)
    await session.flush()

    for suggestion in suggest_mapping(sheet.headers):
        session.add(
            ImportColumnMapping(
                import_job_id=job.id,
                source_column=suggestion.source_column,
                target_field=(suggestion.target_field.value if suggestion.target_field else None),
                confidence=suggestion.confidence,
                is_manual=False,
                sample_values=_samples(sheet, suggestion.source_column),
            )
        )

    await audit_service.record_audit(
        session,
        organization_id=organization_id,
        action=audit_service.ACTION_IMPORT_UPLOAD,
        entity_type="import_job",
        entity_id=str(job.id),
        actor=actor,
        summary=f"Arquivo {safe_name} enviado com {sheet.total_rows} linhas.",
        meta={"columns": sheet.headers, "size_bytes": stored.size_bytes},
        context=context,
    )
    await session.commit()
    await session.refresh(job)
    logger.info(
        "import_uploaded",
        import_id=str(job.id),
        rows=sheet.total_rows,
        columns=len(sheet.headers),
    )
    return job


async def list_import_jobs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    params: PageParams,
    status: ImportStatus | None = None,
) -> tuple[list[ImportJob], int]:
    """Lista importações da organização, mais recentes primeiro."""
    base = select(ImportJob).where(ImportJob.organization_id == organization_id)
    if status is not None:
        base = base.where(ImportJob.status == status)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(ImportJob.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


async def get_import_job(
    session: AsyncSession, *, organization_id: uuid.UUID, import_id: uuid.UUID
) -> ImportJob:
    """Busca uma importação da organização ou falha com 404."""
    job = (
        await session.execute(
            select(ImportJob).where(
                ImportJob.id == import_id, ImportJob.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Importação não encontrada.")
    return job


async def current_mapping(session: AsyncSession, job: ImportJob) -> dict[str, str]:
    """Mapeamento efetivo (coluna → campo canônico) da importação."""
    rows = (
        (
            await session.execute(
                select(ImportColumnMapping).where(ImportColumnMapping.import_job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    return {row.source_column: row.target_field or "" for row in rows}


async def update_mapping(
    session: AsyncSession,
    *,
    job: ImportJob,
    mappings: list[ColumnMappingInput],
    sheet_name: str | None,
    actor: User,
    context: RequestContext | None = None,
) -> ImportJob:
    """Substitui o mapeamento revisado pelo usuário."""
    if job.status is ImportStatus.COMMITTED:
        raise ConflictError("Esta importação já foi confirmada e não pode ser alterada.")

    chosen = [item.target_field for item in mappings if item.target_field is not None]
    duplicates = {field.value for field in chosen if chosen.count(field) > 1}
    if duplicates:
        raise ValidationError(
            "Um mesmo campo canônico não pode receber duas colunas.",
            details={"fields": sorted(duplicates)},
        )

    known = set(job.detected_columns)
    unknown = [item.source_column for item in mappings if item.source_column not in known]
    if unknown:
        raise ValidationError(
            "Colunas informadas não existem no arquivo.", details={"columns": unknown}
        )

    sheet = await _load_sheet(job, sheet_name=sheet_name)
    await session.execute(
        delete(ImportColumnMapping).where(ImportColumnMapping.import_job_id == job.id)
    )
    for item in mappings:
        session.add(
            ImportColumnMapping(
                import_job_id=job.id,
                source_column=item.source_column,
                target_field=item.target_field.value if item.target_field else None,
                confidence=1.0 if item.target_field else 0.0,
                is_manual=True,
                sample_values=_samples(sheet, item.source_column),
            )
        )
    if sheet_name:
        job.sheet_name = sheet.active_sheet
        job.detected_columns = sheet.headers
        job.total_rows = sheet.total_rows
    job.status = ImportStatus.MAPPED

    await audit_service.record_audit(
        session,
        organization_id=job.organization_id,
        action=audit_service.ACTION_IMPORT_MAPPING,
        entity_type="import_job",
        entity_id=str(job.id),
        actor=actor,
        summary="Mapeamento de colunas revisado.",
        meta={
            "mapping": {
                item.source_column: (item.target_field.value if item.target_field else None)
                for item in mappings
            }
        },
        context=context,
    )
    await session.commit()
    await session.refresh(job)
    return job


async def build_preview(
    session: AsyncSession, *, job: ImportJob, limit: int = PREVIEW_ROWS
) -> dict[str, Any]:
    """Monta a prévia com mapeamento atual, linhas normalizadas e pendências."""
    sheet = await _load_sheet(job)
    mapping = await current_mapping(session, job)
    for header in sheet.headers:
        mapping.setdefault(header, "")

    suggestions: list[MappingSuggestion] = suggest_mapping(sheet.headers)
    results, _ = validate_rows(
        sheet.rows[:limit],
        mapping=mapping,
        all_columns=sheet.headers,
        first_row_number=FIRST_DATA_ROW,
    )
    mapped_fields = {value for value in mapping.values() if value}
    return {
        "import_id": job.id,
        "status": job.status,
        "headers": sheet.headers,
        "available_sheets": sheet.sheet_names,
        "active_sheet": sheet.active_sheet,
        "delimiter": sheet.delimiter,
        "encoding": sheet.encoding,
        "total_rows_in_file": sheet.total_rows,
        "mapping": {column: (target or None) for column, target in mapping.items()},
        "suggestions": [
            {
                "source_column": item.source_column,
                "target_field": item.target_field,
                "confidence": item.confidence,
                "reason": item.reason,
                "needs_review": item.needs_review,
            }
            for item in suggestions
        ],
        "unmapped_columns": [column for column, target in mapping.items() if not target],
        "missing_required_fields": [
            field.value for field in missing_required_fields(mapped_fields)
        ],
        "rows": [
            {
                "row_number": result.row_number,
                "raw": result.raw,
                "normalized": result.normalized,
                "status": result.status,
                "errors": [issue.as_dict() for issue in result.errors],
                "warnings": [issue.as_dict() for issue in result.warnings],
            }
            for result in results
        ],
    }


async def validate_import(
    session: AsyncSession,
    *,
    job: ImportJob,
    actor: User,
    context: RequestContext | None = None,
) -> ValidationReport:
    """Valida o arquivo inteiro e persiste o resultado linha a linha."""
    if job.status is ImportStatus.COMMITTED:
        raise ConflictError("Esta importação já foi confirmada.")

    mapping = await current_mapping(session, job)
    mapped_fields = {value for value in mapping.values() if value}
    missing = missing_required_fields(mapped_fields)
    if missing:
        raise ValidationError(
            "Mapeie os campos obrigatórios antes de validar.",
            details={"missing_fields": [field.value for field in missing]},
        )

    sheet = await _load_sheet(job)
    results, report = validate_rows(
        sheet.rows,
        mapping=mapping,
        all_columns=sheet.headers,
        first_row_number=FIRST_DATA_ROW,
    )

    await session.execute(delete(RawImportRow).where(RawImportRow.import_job_id == job.id))
    for result in results:
        session.add(
            RawImportRow(
                organization_id=job.organization_id,
                import_job_id=job.id,
                row_number=result.row_number,
                raw_data=result.raw,
                normalized_data=result.normalized,
                status=result.status,
                errors=[issue.as_dict() for issue in result.errors],
                warnings=[issue.as_dict() for issue in result.warnings],
                dedupe_key=result.dedupe_key or None,
                duplicate_of_row=result.duplicate_of_row,
            )
        )

    job.status = ImportStatus.VALIDATED
    job.total_rows = report.total_rows
    job.valid_rows = report.valid_rows
    job.invalid_rows = report.invalid_rows
    job.duplicate_rows = report.duplicate_rows
    job.validated_at = utcnow()
    job.stats = {**job.stats, "validation": report.as_dict()}

    await audit_service.record_audit(
        session,
        organization_id=job.organization_id,
        action=audit_service.ACTION_IMPORT_VALIDATE,
        entity_type="import_job",
        entity_id=str(job.id),
        actor=actor,
        summary=(
            f"Validação concluída: {report.valid_rows} válidas, "
            f"{report.invalid_rows} com erro, {report.duplicate_rows} duplicadas."
        ),
        meta=report.as_dict(),
        context=context,
    )
    await session.commit()
    await session.refresh(job)
    logger.info(
        "import_validated",
        import_id=str(job.id),
        valid=report.valid_rows,
        invalid=report.invalid_rows,
        duplicates=report.duplicate_rows,
    )
    return report


async def _get_or_create_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    monthly_value: Decimal | None,
    cache: dict[str, Plan],
    created: list[str],
) -> Plan:
    """Localiza o plano pelo nome (case-insensitive) ou cria um novo."""
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    plan = (
        await session.execute(
            select(Plan).where(
                Plan.organization_id == organization_id,
                func.lower(Plan.name) == key,
                Plan.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        plan = Plan(
            organization_id=organization_id,
            name=name.strip()[:120],
            monthly_value=monthly_value or Decimal("0.00"),
            description="Criado automaticamente pela importação.",
        )
        session.add(plan)
        await session.flush()
        created.append(plan.name)
    cache[key] = plan
    return plan


async def commit_import(
    session: AsyncSession,
    *,
    job: ImportJob,
    actor: User,
    context: RequestContext | None = None,
) -> dict[str, Any]:
    """Grava os clientes válidos, criando planos e renovações necessárias."""
    if job.status is ImportStatus.COMMITTED:
        raise ConflictError("Esta importação já foi confirmada.")
    if job.status is not ImportStatus.VALIDATED:
        raise ConflictError("Valide a importação antes de confirmar.")

    rows = (
        (
            await session.execute(
                select(RawImportRow)
                .where(
                    RawImportRow.import_job_id == job.id,
                    RawImportRow.status == RowStatus.VALID,
                )
                .order_by(RawImportRow.row_number)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ConflictError("Nenhuma linha válida para importar.")

    plan_cache: dict[str, Plan] = {}
    created_plans: list[str] = []
    created_customers = 0
    updated_customers = 0
    created_renewals = 0

    for row in rows:
        data = row.normalized_data
        name = data.get(CanonicalField.CUSTOMER_NAME.value)
        if not name:
            continue
        monthly_value = (
            Decimal(str(data[CanonicalField.MONTHLY_VALUE.value]))
            if data.get(CanonicalField.MONTHLY_VALUE.value)
            else None
        )
        plan: Plan | None = None
        plan_name = data.get(CanonicalField.PLAN_NAME.value)
        if plan_name:
            plan = await _get_or_create_plan(
                session,
                organization_id=job.organization_id,
                name=str(plan_name),
                monthly_value=monthly_value,
                cache=plan_cache,
                created=created_plans,
            )

        status_value = data.get(CanonicalField.CUSTOMER_STATUS.value)
        status = CustomerStatus(status_value) if status_value else CustomerStatus.ACTIVE
        start_date = _as_date(data.get(CanonicalField.START_DATE.value))
        renewal_date = _as_date(data.get(CanonicalField.RENEWAL_DATE.value))

        existing = (
            await session.execute(
                select(Customer).where(
                    Customer.organization_id == job.organization_id,
                    Customer.dedupe_key == row.dedupe_key,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            customer = Customer(
                organization_id=job.organization_id,
                name=str(name),
                email=data.get(CanonicalField.EMAIL.value),
                phone=data.get(CanonicalField.PHONE.value),
                document=data.get(CanonicalField.DOCUMENT.value),
                status=status,
                plan_id=plan.id if plan else None,
                monthly_value=monthly_value or (plan.monthly_value if plan else Decimal("0.00")),
                start_date=start_date,
                renewal_date=renewal_date,
                source=data.get(CanonicalField.SOURCE.value) or "importacao",
                notes=data.get(CanonicalField.NOTES.value),
                dedupe_key=row.dedupe_key or f"row:{job.id}:{row.row_number}",
                import_job_id=job.id,
            )
            session.add(customer)
            await session.flush()
            created_customers += 1
            action = audit_service.ACTION_CUSTOMER_CREATE
            summary = f"Cliente {customer.name} criado pela importação."
        else:
            customer = existing
            before = _customer_snapshot(customer)
            customer.name = str(name)
            for attribute, value in (
                ("email", data.get(CanonicalField.EMAIL.value)),
                ("phone", data.get(CanonicalField.PHONE.value)),
                ("document", data.get(CanonicalField.DOCUMENT.value)),
                ("source", data.get(CanonicalField.SOURCE.value)),
                ("notes", data.get(CanonicalField.NOTES.value)),
                ("start_date", start_date),
                ("renewal_date", renewal_date),
            ):
                if value is not None:
                    setattr(customer, attribute, value)
            if monthly_value is not None:
                customer.monthly_value = monthly_value
            if plan is not None:
                customer.plan_id = plan.id
            if status_value:
                customer.status = status
            customer.import_job_id = job.id
            updated_customers += 1
            action = audit_service.ACTION_CUSTOMER_UPDATE
            summary = f"Cliente {customer.name} atualizado pela importação."
            await audit_service.record_audit(
                session,
                organization_id=job.organization_id,
                action=action,
                entity_type="customer",
                entity_id=str(customer.id),
                actor=actor,
                summary=summary,
                meta={
                    "import_job_id": str(job.id),
                    "row_number": row.row_number,
                    "changes": audit_service.build_diff(before, _customer_snapshot(customer)),
                },
                context=context,
            )

        if existing is None:
            await audit_service.record_audit(
                session,
                organization_id=job.organization_id,
                action=action,
                entity_type="customer",
                entity_id=str(customer.id),
                actor=actor,
                summary=summary,
                meta={"import_job_id": str(job.id), "row_number": row.row_number},
                context=context,
            )

        if renewal_date is not None:
            exists = (
                await session.execute(
                    select(Renewal.id).where(
                        Renewal.organization_id == job.organization_id,
                        Renewal.customer_id == customer.id,
                        Renewal.due_date == renewal_date,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    Renewal(
                        organization_id=job.organization_id,
                        customer_id=customer.id,
                        plan_id=customer.plan_id,
                        due_date=renewal_date,
                        amount=customer.monthly_value,
                        status=RenewalStatus.SCHEDULED,
                        notes="Criada pela importação.",
                    )
                )
                created_renewals += 1

        row.status = RowStatus.IMPORTED
        row.customer_id = customer.id

    job.status = ImportStatus.COMMITTED
    job.imported_rows = created_customers
    job.updated_rows = updated_customers
    job.committed_at = utcnow()
    job.stats = {
        **job.stats,
        "commit": {
            "created_customers": created_customers,
            "updated_customers": updated_customers,
            "created_plans": created_plans,
            "created_renewals": created_renewals,
        },
    }

    await audit_service.record_audit(
        session,
        organization_id=job.organization_id,
        action=audit_service.ACTION_IMPORT_COMMIT,
        entity_type="import_job",
        entity_id=str(job.id),
        actor=actor,
        summary=(
            f"Importação confirmada: {created_customers} clientes criados, "
            f"{updated_customers} atualizados."
        ),
        meta=job.stats.get("commit", {}),
        context=context,
    )
    await dispatcher.dispatch_event(
        session,
        organization_id=job.organization_id,
        event_type=dispatcher.EVENT_IMPORT_COMPLETED,
        idempotency_key=f"import-{job.id}",
        payload={
            "import_id": str(job.id),
            "filename": job.original_filename,
            "created_customers": created_customers,
            "updated_customers": updated_customers,
            "created_renewals": created_renewals,
            "invalid_rows": job.invalid_rows,
            "duplicate_rows": job.duplicate_rows,
        },
    )
    await session.commit()
    await session.refresh(job)
    logger.info(
        "import_committed",
        import_id=str(job.id),
        created=created_customers,
        updated=updated_customers,
    )
    return {
        "import_id": job.id,
        "status": job.status,
        "created_customers": created_customers,
        "updated_customers": updated_customers,
        "created_plans": len(created_plans),
        "created_renewals": created_renewals,
        "skipped_invalid": job.invalid_rows,
        "skipped_duplicates": job.duplicate_rows,
        "committed_at": job.committed_at,
        "message": (
            f"{created_customers} clientes criados e {updated_customers} atualizados. "
            f"{job.invalid_rows} linhas com erro e {job.duplicate_rows} duplicadas foram ignoradas."
        ),
    }


def _as_date(value: Any) -> date | None:
    """Converte a data normalizada (string ISO) de volta para ``date``."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _customer_snapshot(customer: Customer) -> dict[str, Any]:
    """Estado auditável de um cliente."""
    return {
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "document": customer.document,
        "status": customer.status.value,
        "plan_id": str(customer.plan_id) if customer.plan_id else None,
        "monthly_value": str(customer.monthly_value),
        "start_date": customer.start_date.isoformat() if customer.start_date else None,
        "renewal_date": customer.renewal_date.isoformat() if customer.renewal_date else None,
        "source": customer.source,
        "notes": customer.notes,
    }


async def list_row_errors(
    session: AsyncSession,
    *,
    job: ImportJob,
    params: PageParams,
    only_status: RowStatus | None = None,
) -> tuple[list[RawImportRow], int]:
    """Lista linhas com erro ou duplicadas de uma importação."""
    statuses = [only_status] if only_status else [RowStatus.INVALID, RowStatus.DUPLICATE]
    base = select(RawImportRow).where(
        RawImportRow.import_job_id == job.id, RawImportRow.status.in_(statuses)
    )
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = (
        (
            await session.execute(
                base.order_by(RawImportRow.row_number).offset(params.offset).limit(params.page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


def build_recommendations(job: ImportJob) -> list[str]:
    """Sugestões acionáveis com base no resultado da importação."""
    recommendations: list[str] = []
    validation = job.stats.get("validation") if isinstance(job.stats, dict) else None
    if not validation:
        recommendations.append("Execute a validação para gerar o relatório completo.")
        return recommendations

    if validation.get("invalid_rows"):
        recommendations.append(
            f"Corrija {validation['invalid_rows']} linha(s) com erro na planilha de origem "
            "e reenvie apenas as linhas corrigidas."
        )
    if validation.get("duplicate_rows"):
        recommendations.append(
            f"{validation['duplicate_rows']} linha(s) duplicada(s) foram ignoradas. "
            "Confira o critério de deduplicação no relatório."
        )
    for field_name, rate in (validation.get("fill_rate") or {}).items():
        if rate < 0.6:
            recommendations.append(
                f"O campo “{field_name}” está preenchido em apenas {rate:.0%} das linhas."
            )
    if not validation.get("mapped_fields") or "renewal_date" not in validation.get(
        "mapped_fields", []
    ):
        recommendations.append(
            "Mapeie a data de renovação para habilitar os indicadores de renovação."
        )
    if not recommendations:
        recommendations.append("Nenhuma pendência encontrada nesta importação.")
    return recommendations
