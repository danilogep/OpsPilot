"""Conteúdo sintético da base de conhecimento usado no seed de demonstração.

Todos os textos são **fictícios**, escritos para o cenário da empresa
demonstrativa "Acme Serviços". Nenhuma informação real de clientes.
"""

from __future__ import annotations

from typing import NamedTuple


class DemoDocument(NamedTuple):
    """Documento sintético da base de conhecimento."""

    title: str
    filename: str
    tags: list[str]
    body: str


DEMO_DOCUMENTS: list[DemoDocument] = [
    DemoDocument(
        title="Política de renovação de contratos",
        filename="politica-de-renovacao.md",
        tags=["renovação", "contratos"],
        body="""# Política de renovação de contratos

## Prazos
Os contratos da Acme Serviços são renovados automaticamente por 12 meses, salvo
manifestação contrária. O time de Customer Success deve iniciar o contato de
renovação **45 dias antes** da data de vencimento e registrar a tentativa no
OpsPilot.

## Escalonamento
Se não houver resposta até 15 dias antes do vencimento, o caso é escalado para a
coordenação comercial. Contratos acima de R$ 1.500,00 mensais são tratados como
renovação crítica e exigem reunião com o responsável pela conta.

## Reajuste
O reajuste anual segue o IPCA acumulado, limitado a 8% ao ano. Clientes com mais
de 24 meses de contrato têm direito a 1 mês de carência no reajuste.

## Registro obrigatório
Toda renovação confirmada precisa de: data de confirmação, valor acordado,
responsável pelo contato e observações sobre condições especiais.
""",
    ),
    DemoDocument(
        title="FAQ dos planos comerciais",
        filename="faq-planos.md",
        tags=["planos", "comercial"],
        body="""# FAQ dos planos comerciais

## Quais planos existem?
Essencial, Profissional, Avançado, Enterprise e Suporte Pontual. O plano
Essencial atende microempresas com até 3 usuários. O Profissional permite 10
usuários e inclui relatórios mensais. O Avançado adiciona integrações e
atendimento prioritário. O Enterprise é negociado caso a caso.

## É possível trocar de plano no meio do contrato?
Sim. O upgrade é imediato e proporcional ao período restante. O downgrade só
entra em vigor no ciclo seguinte, com aviso mínimo de 10 dias.

## Qual o período mínimo?
Planos mensais têm período mínimo de 3 meses. O Suporte Pontual é cobrado por
demanda, sem período mínimo.

## Há desconto para pagamento anual?
Sim: 10% de desconto no pagamento anual antecipado, aplicável a todos os planos
recorrentes.
""",
    ),
    DemoDocument(
        title="Playbook comercial de qualificação",
        filename="playbook-comercial.md",
        tags=["leads", "vendas"],
        body="""# Playbook comercial de qualificação

## Critérios de qualificação
Um lead é considerado qualificado quando possui: contato válido (e-mail ou
telefone), segmento compatível com o portfólio, porte entre micro e média
empresa e interesse declarado em pelo menos um plano recorrente.

## Segmentos prioritários
Serviços profissionais, saúde, educação, varejo local e tecnologia. Segmentos
fora dessa lista exigem aprovação da coordenação antes da proposta.

## Cadência de contato
Primeiro contato em até 1 dia útil após a entrada do lead. Depois: dia 3, dia 7
e dia 14. Após 4 tentativas sem resposta, o lead é marcado como perdido com o
motivo "sem resposta".

## Proposta
A proposta deve conter escopo, valor mensal, prazo de implantação e condição de
pagamento. Descontos acima de 15% precisam de aprovação.
""",
    ),
    DemoDocument(
        title="SLA de atendimento e suporte",
        filename="sla-atendimento.md",
        tags=["suporte", "sla"],
        body="""# SLA de atendimento e suporte

## Horário
Atendimento de segunda a sexta, das 9h às 18h (horário de Brasília), exceto
feriados nacionais.

## Prazos de primeira resposta
- Incidente crítico (serviço indisponível): 2 horas úteis.
- Incidente alto (função principal degradada): 4 horas úteis.
- Dúvida ou solicitação: 1 dia útil.

## Prazos de solução
Incidentes críticos têm meta de solução em 1 dia útil; altos, 3 dias úteis;
demais solicitações, 5 dias úteis. Clientes do plano Avançado e Enterprise têm
fila prioritária.

## Créditos
Indisponibilidade superior a 8 horas no mês gera crédito de 5% da mensalidade,
solicitado pelo cliente em até 30 dias.
""",
    ),
    DemoDocument(
        title="Política de cancelamento",
        filename="politica-de-cancelamento.md",
        tags=["cancelamento", "churn"],
        body="""# Política de cancelamento

## Aviso prévio
O cancelamento exige aviso prévio de **30 dias**, enviado por e-mail para o
endereço de atendimento. A cobrança do ciclo em andamento não é devolvida.

## Multa
Cancelamento antes do período mínimo de 3 meses gera multa equivalente a 30% das
mensalidades restantes do período mínimo.

## Motivos mais frequentes
Historicamente, os motivos registrados são: redução de orçamento, troca por
concorrente, encerramento da operação e insatisfação com prazo de suporte.

## Retenção
Antes de efetivar o cancelamento, o time deve oferecer: revisão de plano,
pausa de até 60 dias ou desconto de retenção de até 15% por 3 meses.

## Reativação
Clientes cancelados há menos de 6 meses podem reativar mantendo o valor
anterior, sem nova taxa de implantação.
""",
    ),
    DemoDocument(
        title="Guia de cobrança e inadimplência",
        filename="guia-de-cobranca.md",
        tags=["financeiro", "cobrança"],
        body="""# Guia de cobrança e inadimplência

## Vencimento
As mensalidades vencem no dia 10 de cada mês. O boleto é enviado com 7 dias de
antecedência.

## Régua de cobrança
- D+1: lembrança automática por e-mail.
- D+5: contato por telefone ou WhatsApp.
- D+15: suspensão parcial do serviço e aviso formal.
- D+30: cliente marcado como atrasado no OpsPilot e envio para negociação.

## Negociação
É permitido parcelar o débito em até 3 vezes, sem juros, com registro da
negociação no histórico do cliente.

## Clientes atrasados
Um cliente com situação "atrasado" não deve receber proposta de upgrade até a
regularização do débito.
""",
    ),
    DemoDocument(
        title="Processo de onboarding de novos clientes",
        filename="processo-de-onboarding.md",
        tags=["onboarding", "operação"],
        body="""# Processo de onboarding de novos clientes

## Etapas
1. Assinatura do contrato e registro do cliente no OpsPilot.
2. Reunião de kickoff em até 5 dias úteis.
3. Coleta de dados e importação das planilhas do cliente.
4. Configuração dos planos e das datas de renovação.
5. Treinamento de 1 hora com a equipe do cliente.
6. Acompanhamento semanal durante os 30 primeiros dias.

## Responsabilidades
O time de implantação conduz as etapas 1 a 4. O time de Customer Success assume
a partir da etapa 5.

## Critério de conclusão
O onboarding é concluído quando o cliente registra o primeiro mês de uso com
dados importados e a data de renovação preenchida.
""",
    ),
    DemoDocument(
        title="Tabela de descontos autorizados",
        filename="tabela-de-descontos.md",
        tags=["comercial", "descontos"],
        body="""# Tabela de descontos autorizados

## Por alçada
- Consultor comercial: até 10%.
- Coordenação comercial: até 20%.
- Diretoria: acima de 20%.

## Por situação
- Pagamento anual antecipado: 10%.
- Indicação de cliente ativo: 5% para quem indica e 5% para o indicado, por 3 meses.
- Retenção de cliente em risco: até 15% por 3 meses.
- Órgãos do terceiro setor: 12% permanente, com comprovação.

## Regras
Descontos não são cumulativos, exceto indicação somada a pagamento anual.
Todo desconto precisa constar na proposta e no registro do cliente.
""",
    ),
    DemoDocument(
        title="Diretrizes internas de uso de dados",
        filename="diretrizes-de-dados.md",
        tags=["segurança", "lgpd"],
        body="""# Diretrizes internas de uso de dados

## Princípios
Coletamos apenas os dados necessários à prestação do serviço. Planilhas enviadas
pelos clientes são tratadas como informação confidencial.

## Acesso
O acesso aos dados segue o perfil do usuário: administradores têm acesso total,
analistas acessam dados operacionais e visualizadores apenas consultam.

## Retenção
Arquivos de importação são mantidos por 90 dias e depois descartados. Registros
de auditoria são mantidos por 24 meses.

## Uso de IA
Resumos e sugestões geradas por IA devem sempre indicar as fontes consultadas.
É proibido enviar dados sensíveis para provedores externos sem autorização
formal. No ambiente de demonstração, o provedor padrão é um mock local.
""",
    ),
    DemoDocument(
        title="Roteiro de contato por mensagem",
        filename="roteiro-de-contato.md",
        tags=["comercial", "mensagens"],
        body="""# Roteiro de contato por mensagem

## Primeiro contato com lead
Apresentar-se, citar a origem do contato, fazer uma pergunta sobre a operação do
cliente e propor uma conversa de 15 minutos. Nunca enviar proposta no primeiro
contato.

## Lembrete de renovação
Mencionar o tempo de parceria, confirmar a data de vencimento, informar o valor
e perguntar se há mudança de escopo para o próximo ciclo.

## Retomada de lead sem resposta
Retomar o último assunto tratado, oferecer um material útil e dar uma saída
clara ("se não for o momento, me avise que retomo em 3 meses").

## Boas práticas
Mensagens curtas, sem jargão, com um único pedido por mensagem. Toda mensagem
enviada deve ser registrada no histórico do lead ou do cliente.
""",
    ),
]
