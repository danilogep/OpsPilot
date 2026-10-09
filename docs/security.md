# Segurança e limites de operação
Implementado: hash Argon2, JWT com validade, autorização por papel, escopo de organização nos serviços, validação de entrada/arquivos, exclusão lógica, erros padronizados, HMAC e idempotência em webhooks, auditoria.

Antes de publicar: substituir todos os segredos de demonstração, desabilitar seed de usuários públicos, restringir CORS, habilitar TLS, backups/restauração e limites de requisição/upload no proxy. Restringir rede de saída de webhooks; proteger credenciais com secret manager. Avaliar autorização e isolamento de organização com dados reais e testes adicionais.

O frontend usa localStorage para JWT: uma falha XSS comprometeria a sessão. Não renderiza HTML da IA. Evolução recomendada: sessão via cookie HttpOnly e proteção CSRF.
Busca textual e fontes reduzem respostas sem fundamento, mas não garantem veracidade de um LLM externo. Conteúdo importado deve ser tratado como dado e pode conter instruções maliciosas; não concede ferramentas de shell/rede aos documentos.
Logs não devem conter tokens. Resumos de consultas e dados de auditoria podem conter dados digitados pelo usuário: definir retenção e acesso para uso real.
O upload é processado sincronamente, limitado pela configuração; PDF sem texto não recebe OCR.
Este projeto não possui certificação de segurança nem foi auditado para uso público multiempresa.
