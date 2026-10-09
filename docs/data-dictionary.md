# Dicionário dos dados
| Entidade | Finalidade |
| --- | --- |
| Organization | Limite de acesso e configuração da empresa |
| User / Role | Credenciais, papel e atividade |
| Customer | Nome, contato, plano, status, valor mensal, início e renovação |
| Plan | Catálogo comercial, código, descrição e preço |
| Renewal | Vencimento, valor e situação de renovação de cliente |
| Lead / LeadEvent | Oportunidade, prioridade, critérios e histórico |
| ImportJob / ImportColumnMapping / RawImportRow | Arquivo, mapeamento, linha original e validação |
| KnowledgeDocument / DocumentChunk | Fonte documental e trechos pesquisáveis |
| AgentDefinition / AgentRun | Configuração de agente e rastreamento de ferramentas |
| LLMUsage | Provider, modelo, tokens, versão do prompt e custo estimado |
| WebhookEvent | Entrada/saída, idempotência, assinatura, status e tentativas |
| AuditEvent | Ator, ação, entidade, resumo e correlation_id |

Identificadores UUID. Datas de calendário ISO YYYY-MM-DD; timestamps em UTC. Dinheiro usa Decimal no backend e string JSON; apresentação em BRL.
Receita mensal estimada soma contratos ativos e atrasados. Score de leads é uma regra de priorização, não previsão estatística de conversão.
Valores e pessoas do seed são sintéticos. RawImportRow conserva a origem e os erros de normalização para revisão.
