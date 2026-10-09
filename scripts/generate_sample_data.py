"""Gera as planilhas sintéticas de demonstração em ``data/samples``.

Os arquivos são **propositalmente imperfeitos**: cabeçalhos em português com
variações, duplicidades, campos vazios, datas inválidas e valores monetários em
formatos diferentes. É isso que torna a demonstração do pipeline de importação
convincente.

Uso:

    python scripts/generate_sample_data.py            # grava em data/samples
    python scripts/generate_sample_data.py --out /tmp # outro diretório

Determinístico: a mesma semente produz sempre os mesmos arquivos.
"""

from __future__ import annotations

import argparse
import csv
import random
import unicodedata
from datetime import date, timedelta
from pathlib import Path

SEED = 20260101
CUSTOMER_ROWS = 120
LEAD_ROWS = 60

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "samples"

# Cabeçalhos "do mundo real": variados, com acento e espaços.
CUSTOMER_HEADERS = [
    "Razão Social",
    "E-mail",
    "Celular / WhatsApp",
    "CNPJ",
    "Plano Contratado",
    "Situação",
    "Data de Adesão",
    "Vencimento",
    "Mensalidade (R$)",
    "Como nos conheceu",
    "Observações",
]

LEAD_HEADERS = [
    "Nome",
    "Empresa",
    "E-mail",
    "Telefone",
    "Origem",
    "Segmento",
    "Porte",
    "Interesse",
    "Valor estimado",
    "Última interação",
]

COMPANIES = (
    "Padaria Aurora", "Clínica Vida", "Studio Lumen", "Mercado Bom Preço",
    "Oficina Trilho", "Escola Horizonte", "Pet Shop Amigo", "Casa das Tintas",
    "Transportes Rota", "Farmácia Saúde", "Contabilidade Prisma", "Advocacia Mendes",
    "Restaurante Sabor", "Academia Força", "Gráfica Impacto", "Lavanderia Clara",
    "Marcenaria Cedro", "Floricultura Jardim", "Ótica Visão", "Doceria Mel",
    "Barbearia Nobre", "Pousada Mar Azul", "Agência Vértice", "Imobiliária Lar",
    "Serralheria Ferro", "Papelaria Nota", "Distribuidora Norte", "Auto Center Giro",
    "Creche Pequeno Mundo", "Buffet Festa Boa",
)
SUFFIXES = ("Ltda", "ME", "EIRELI", "& Cia", "Serviços", "Comércio")
PLANS = ("Essencial", "Profissional", "Avançado", "Enterprise", "Suporte Pontual")
PLAN_VALUES = {
    "Essencial": "199,00",
    "Profissional": "499,00",
    "Avançado": "899,00",
    "Enterprise": "1.890,00",
    "Suporte Pontual": "150,00",
}
STATUSES = ("Ativo", "ativo", "ATIVO", "Atrasado", "Inadimplente", "Cancelado", "Prospect", "")
SOURCES = ("Indicação", "Site", "Google Ads", "Evento", "Prospecção", "Redes sociais", "")
FIRST_NAMES = (
    "Mariana", "Rafael", "Juliana", "Thiago", "Patrícia", "Eduardo", "Camila",
    "Vinícius", "Fernanda", "Lucas", "Bianca", "Gustavo", "Larissa", "Felipe",
)
LAST_NAMES = (
    "Silva", "Souza", "Oliveira", "Costa", "Pereira", "Almeida", "Nunes", "Carvalho",
)
SEGMENTS = (
    "serviços profissionais", "saúde", "educação", "varejo local", "tecnologia",
    "alimentação", "logística", "construção", "contabilidade", "indústria",
)
SIZES = ("MEI", "Micro", "Pequena", "Média", "Grande", "")
INTERESTS = (
    "organizar a base de clientes", "controlar renovações", "reduzir inadimplência",
    "painel de indicadores", "importar planilhas antigas", "",
)
#: Datas inválidas usadas de propósito para demonstrar o relatório de erros.
BAD_DATES = ("31/02/2026", "data a definir", "0000-00-00", "2026-13-05", "amanhã")
#: Valores monetários em formatos diferentes, inclusive inválidos.
MONEY_VARIANTS = ("R$ 1.250,00", "1250,00", "1250.00", "R$ 980", "mil reais", "")


def slugify(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in ascii_only)
    return "-".join(part for part in cleaned.split("-") if part)


def _fake_cnpj(rng: random.Random, *, masked: bool = True) -> str:
    digits = "".join(str(rng.randint(0, 9)) for _ in range(14))
    if not masked:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _phone(rng: random.Random, style: int) -> str:
    ddd = rng.choice([11, 19, 21, 31, 41, 51, 62, 71, 81, 85])
    number = rng.randint(90000000, 99999999)
    if style == 0:
        return f"({ddd}) 9{number:08d}"[:16]
    if style == 1:
        return f"{ddd}9{number:08d}"
    if style == 2:
        return f"+55 {ddd} 9{str(number)[:4]}-{str(number)[4:]}"
    if style == 3:
        return f"9{number:08d}"  # sem DDD: erro proposital
    return ""


def build_customer_rows(rng: random.Random, today: date) -> list[list[str]]:
    """Monta as linhas do arquivo de clientes, com imperfeições controladas."""
    rows: list[list[str]] = []
    for index in range(CUSTOMER_ROWS):
        company = COMPANIES[index % len(COMPANIES)]
        suffix = SUFFIXES[index % len(SUFFIXES)]
        name = f"{company} {suffix}"
        plan = PLANS[index % len(PLANS)]

        email = f"contato@{slugify(company)}{index}.com.br"
        if index % 17 == 0:
            email = ""  # sem contato
        elif index % 23 == 0:
            email = f"contato@{slugify(company)}"  # e-mail inválido (sem TLD)

        start = today - timedelta(days=rng.randint(90, 1200))
        renewal = today + timedelta(days=rng.choice([3, 5, 12, 25, 40, 90, 180, -10, -40]))
        start_text = start.strftime("%d/%m/%Y") if index % 3 else start.isoformat()
        renewal_text = renewal.strftime("%d/%m/%Y")
        if index % 19 == 0:
            renewal_text = rng.choice(BAD_DATES)  # data inválida proposital
        elif index % 29 == 0:
            renewal_text = ""

        value = PLAN_VALUES[plan]
        if index % 11 == 0:
            value = rng.choice(MONEY_VARIANTS)

        rows.append(
            [
                name if index % 7 else name.upper(),
                email,
                _phone(rng, index % 5),
                _fake_cnpj(rng, masked=bool(index % 2)),
                plan if index % 13 else plan.lower(),
                STATUSES[index % len(STATUSES)],
                start_text,
                renewal_text,
                value,
                SOURCES[index % len(SOURCES)],
                "Cliente sintético para demonstração." if index % 4 == 0 else "",
            ]
        )

    # Duplicidades propositais: mesmo e-mail e mesmo nome em linhas diferentes.
    for source_index in (0, 5, 9):
        duplicated = list(rows[source_index])
        duplicated[10] = "Linha duplicada proposital (mesmo e-mail)."
        rows.append(duplicated)
    near_duplicate = list(rows[3])
    near_duplicate[1] = ""  # sem e-mail, mas mesmo CNPJ
    near_duplicate[10] = "Duplicidade por documento."
    rows.append(near_duplicate)
    return rows


def build_lead_rows(rng: random.Random, today: date) -> list[list[str]]:
    """Monta as linhas do arquivo de leads."""
    rows: list[list[str]] = []
    for index in range(LEAD_ROWS):
        person = f"{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[index % len(LAST_NAMES)]}"
        company = COMPANIES[(index * 7) % len(COMPANIES)]
        email = "" if index % 13 == 0 else f"{slugify(person)}{index}@exemplo.com.br"
        interaction = today - timedelta(days=rng.choice([1, 2, 5, 9, 20, 45, 70]))
        rows.append(
            [
                person,
                company,
                email,
                _phone(rng, index % 5),
                SOURCES[index % len(SOURCES)] or "Indicação",
                SEGMENTS[index % len(SEGMENTS)],
                SIZES[index % len(SIZES)],
                INTERESTS[index % len(INTERESTS)],
                rng.choice(["0", "350,00", "600,00", "1.200,00", "1800", "2.500,00", ""]),
                interaction.strftime("%d/%m/%Y"),
            ]
        )
    return rows


def write_csv(path: Path, headers: list[str], rows: list[list[str]], *, delimiter: str = ";") -> None:
    """Grava um CSV com BOM (compatível com Excel pt-BR)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(rows)


def write_xlsx(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    """Grava a mesma base em XLSX, com datas e valores como tipos nativos."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:  # pragma: no cover - openpyxl é dependência do backend
        print("openpyxl não instalado: XLSX não gerado.")
        return

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Clientes"
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    widths = (34, 32, 20, 22, 18, 14, 16, 16, 16, 18, 40)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width

    notes = workbook.create_sheet("Leia-me")
    notes["A1"] = "Arquivo sintético de demonstração do OpsPilot"
    notes["A2"] = "Contém erros e duplicidades propositais para exercitar a validação."
    notes["A3"] = "Nenhum dado real de pessoa ou empresa."
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def write_knowledge(path: Path) -> None:
    """Grava um documento de conhecimento de exemplo para upload manual."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Manual rápido de operação — Acme Serviços (exemplo sintético)

## Renovações
O contato de renovação começa 45 dias antes do vencimento. Contratos acima de
R$ 1.500,00 mensais são tratados como renovação crítica.

## Cancelamento
O cancelamento exige aviso prévio de 30 dias. Antes de efetivar, oferecer
revisão de plano, pausa de até 60 dias ou desconto de retenção de até 15%.

## Cobrança
Mensalidades vencem no dia 10. A régua de cobrança é D+1 (e-mail), D+5
(telefone), D+15 (suspensão parcial) e D+30 (negociação).

## Descontos
Consultor até 10%, coordenação até 20%, diretoria acima de 20%. Pagamento anual
antecipado recebe 10%.

> Documento fictício, criado apenas para demonstrar a base de conhecimento.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera planilhas sintéticas do OpsPilot")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="diretório de saída")
    args = parser.parse_args()

    rng = random.Random(SEED)
    today = date.today()
    out: Path = args.out

    customer_rows = build_customer_rows(rng, today)
    lead_rows = build_lead_rows(rng, today)

    write_csv(out / "customers.csv", CUSTOMER_HEADERS, customer_rows)
    write_xlsx(out / "customers.xlsx", CUSTOMER_HEADERS, customer_rows)
    write_csv(out / "leads.csv", LEAD_HEADERS, lead_rows, delimiter=",")
    write_knowledge(out / "knowledge.md")

    print(f"Arquivos gerados em {out}:")
    print(f"  customers.csv   {len(customer_rows)} linhas (com erros e duplicidades)")
    print(f"  customers.xlsx  {len(customer_rows)} linhas")
    print(f"  leads.csv       {len(lead_rows)} linhas")
    print("  knowledge.md    documento de exemplo")


if __name__ == "__main__":
    main()
