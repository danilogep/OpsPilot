"""Provider de IA local (mock) — padrão do projeto.

Não faz chamada de rede, não precisa de chave e é **determinístico**: a mesma
entrada produz sempre a mesma saída. A resposta é montada exclusivamente a
partir do ``context`` (dados já consultados no banco e trechos recuperados da
base de conhecimento), o que elimina alucinação por construção.

Quando o contexto não traz evidência, a resposta é a frase padrão do produto:
``Não encontrei evidências suficientes nos dados disponíveis.``
"""

from __future__ import annotations

import json
from typing import Any

from app.core.formatting import format_brl, format_date_br, format_int
from app.integrations.llm.base import (
    LLMFeature,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    estimate_tokens,
)

NO_EVIDENCE_MESSAGE = "Não encontrei evidências suficientes nos dados disponíveis."


class MockProvider(LLMProvider):
    """Gera respostas fundamentadas sem depender de serviço externo."""

    name = "mock"
    default_model = "mock"
    supports_json = True
    is_mock = True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Monta a resposta conforme a funcionalidade solicitada."""
        renderers = {
            LLMFeature.ASSISTANT: _render_assistant,
            LLMFeature.LEAD_CLASSIFIER: _render_lead_classifier,
            LLMFeature.RENEWAL_SUMMARY: _render_renewal_summary,
            LLMFeature.MESSAGE_DRAFT: _render_message_draft,
            LLMFeature.AGENT: _render_agent,
        }
        renderer = renderers.get(request.feature, _render_generic)
        text = renderer(request)
        prompt_size = estimate_tokens(request.system + request.user_text)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model or self.default_model,
            input_tokens=prompt_size + estimate_tokens(json.dumps(request.context, default=str)),
            output_tokens=estimate_tokens(text),
            is_mock=True,
        )


def _facts(context: dict[str, Any]) -> list[dict[str, Any]]:
    facts = context.get("facts")
    return list(facts) if isinstance(facts, list) else []


def _passages(context: dict[str, Any]) -> list[dict[str, Any]]:
    passages = context.get("knowledge")
    return list(passages) if isinstance(passages, list) else []


def _format_fact(fact: dict[str, Any]) -> str:
    label = str(fact.get("label", "indicador"))
    value = fact.get("value")
    kind = str(fact.get("kind", "text"))
    if kind == "money":
        rendered = format_brl(value)
    elif kind == "count":
        rendered = format_int(value)
    elif kind == "date":
        rendered = format_date_br(value)
    else:
        rendered = str(value)
    return f"- **{label}:** {rendered}"


def _render_assistant(request: LLMRequest) -> str:
    """Resposta do assistente de dados, com números e raciocínio explícitos."""
    context = request.context
    facts = _facts(context)
    passages = _passages(context)
    if not facts and not passages:
        return (
            f"{NO_EVIDENCE_MESSAGE}\n\n"
            "Para responder a esta pergunta eu preciso de clientes, renovações ou leads "
            "cadastrados, ou de um documento na base de conhecimento que trate do assunto. "
            "Importe uma planilha ou envie um documento e pergunte novamente."
        )

    headline = str(context.get("headline") or "Resumo dos dados encontrados")
    lines = [headline, ""]
    if facts:
        lines.append("**Números usados nesta resposta**")
        lines.extend(_format_fact(fact) for fact in facts)
        lines.append("")
    if passages:
        lines.append("**Trechos da base de conhecimento**")
        for passage in passages[:3]:
            title = str(passage.get("document_title", "documento"))
            excerpt = str(passage.get("excerpt", "")).strip().replace("\n", " ")
            lines.append(f"- *{title}*: “{excerpt[:260]}”")
        lines.append("")
    reasoning = context.get("reasoning")
    if isinstance(reasoning, list) and reasoning:
        lines.append("**Como cheguei a esse resultado**")
        lines.extend(f"{index}. {step}" for index, step in enumerate(reasoning, start=1))
        lines.append("")
    recommendation = context.get("recommendation")
    if recommendation:
        lines.append(f"**Recomendação:** {recommendation}")
    return "\n".join(lines).strip()


def _render_lead_classifier(request: LLMRequest) -> str:
    """Classificação de lead em JSON válido, derivada do score determinístico."""
    context = request.context
    lead = context.get("lead") or {}
    rules = context.get("rules_score") or {}
    score = int(rules.get("score", 0))
    category = str(rules.get("category", "COLD"))
    reasons = [str(item) for item in (rules.get("reasons") or [])][:6]
    risks = [str(item) for item in (rules.get("risks") or [])][:5]
    next_action = str(rules.get("next_step") or "Revisar o cadastro do lead.")

    name = str(lead.get("name") or "este contato")
    company = lead.get("company")
    interest = lead.get("interest")
    target = f"{name} ({company})" if company else name

    if interest:
        message = (
            f"Olá, {name}! Vi que o interesse é {interest}. "
            "Consigo mostrar em 15 minutos como o OpsPilot organiza isso com os seus "
            "próprios dados. Que tal quinta às 10h?"
        )
    else:
        message = (
            f"Olá, {name}! Estou retomando nosso contato para entender a prioridade de "
            f"{company or 'sua empresa'} neste trimestre. Consigo uma conversa de 15 minutos?"
        )

    payload = {
        "score": score,
        "category": category,
        "reasons": reasons or [f"Score {score} calculado pelas regras determinísticas."],
        "risks": risks,
        "next_action": next_action,
        "suggested_message": message,
        "summary": (
            f"{target} está classificado como {category} com score {score}/100 "
            "segundo as regras do OpsPilot."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_renewal_summary(request: LLMRequest) -> str:
    """Resumo executivo de renovações."""
    context = request.context
    indicators = context.get("indicators") or {}
    critical = context.get("critical") or []
    if not indicators and not critical:
        return NO_EVIDENCE_MESSAGE

    due_7 = indicators.get("due_next_7_days", 0)
    due_30 = indicators.get("due_next_30_days", 0)
    overdue = indicators.get("overdue", 0)
    at_risk = indicators.get("amount_at_risk", "0")
    no_contact = indicators.get("customers_without_recent_contact", 0)
    threshold = indicators.get("contact_threshold_days", 45)

    lines = [
        "**Resumo executivo de renovações**",
        "",
        f"Nos próximos 7 dias há {format_int(due_7)} renovação(ões) e, em 30 dias, "
        f"{format_int(due_30)}. Existem {format_int(overdue)} renovação(ões) vencidas em "
        f"aberto e {format_brl(at_risk)} de receita mensal em risco. "
        f"{format_int(no_contact)} cliente(s) estão sem contato há mais de {threshold} dias.",
        "",
    ]
    if critical:
        lines.append("**Clientes críticos**")
        for item in critical[:5]:
            lines.append(
                f"- {item.get('customer_name')} — vence em "
                f"{format_date_br(item.get('due_date'))} "
                f"({format_brl(item.get('amount'))}): {item.get('reason')}"
            )
        lines.append("")
    lines.extend(
        [
            "**Ações recomendadas**",
            "1. Priorizar contato com as renovações vencidas e com as que vencem em 7 dias.",
            "2. Registrar cada tentativa de contato para não repetir abordagem.",
            "3. Revisar os clientes sem contato recente antes do fim do mês.",
        ]
    )
    return "\n".join(lines)


def _render_message_draft(request: LLMRequest) -> str:
    """Rascunho curto de mensagem comercial (nunca enviado automaticamente)."""
    context = request.context
    target = context.get("target") or {}
    name = str(target.get("name") or "cliente")
    purpose = str(context.get("purpose") or "retomar o contato")
    detail = context.get("detail")
    tone = str(context.get("tone") or "cordial e direto")

    pieces = [f"Olá, {name}!"]
    if purpose == "renewal":
        due = format_date_br(target.get("due_date"))
        amount = format_brl(target.get("amount"))
        pieces.append(
            f"Seu contrato renova em {due}, no valor de {amount}. "
            "Posso confirmar a renovação ou prefere revisar o escopo antes?"
        )
    elif purpose == "lead":
        pieces.append(
            "Estou retomando nosso contato para entender sua prioridade agora. "
            "Consigo mostrar em 15 minutos como organizamos clientes e renovações."
        )
    else:
        pieces.append(f"Gostaria de {purpose}.")
    if detail:
        pieces.append(str(detail))
    pieces.append("Fico à disposição.")
    draft = " ".join(pieces)
    return (
        f"{draft}\n\n"
        f"_Tom: {tone}. Rascunho gerado localmente — revise antes de enviar. "
        "O OpsPilot não envia mensagens automaticamente._"
    )


def _render_agent(request: LLMRequest) -> str:
    """Resposta final de um agente, a partir das observações das ferramentas."""
    context = request.context
    observations = context.get("observations") or []
    if not observations:
        return NO_EVIDENCE_MESSAGE
    lines = ["**Conclusão do agente**", ""]
    for observation in observations[:6]:
        tool = observation.get("tool", "ferramenta")
        summary = observation.get("summary", "")
        lines.append(f"- `{tool}`: {summary}")
    conclusion = context.get("conclusion")
    if conclusion:
        lines.extend(["", str(conclusion)])
    return "\n".join(lines)


def _render_generic(request: LLMRequest) -> str:
    """Fallback para funcionalidades sem renderizador dedicado."""
    if not request.context:
        return NO_EVIDENCE_MESSAGE
    return (
        "Resposta gerada pelo provider local de demonstração a partir dos dados "
        f"fornecidos: {json.dumps(request.context, ensure_ascii=False, default=str)[:800]}"
    )
