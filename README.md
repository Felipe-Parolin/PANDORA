# PANDORA

Plataforma para gestão de locação, inspeção, manutenção e transporte de equipamentos, com dados da empresa configuráveis por instalação.

Este repositório contém a primeira versão funcional do MVP: API em Python/Django REST, frontend em Vue 3 e PostgreSQL 17 como banco principal. O SQLite permanece apenas como opção explícita para testes isolados.

## O que já está implementado

- autenticação JWT com ACL aplicada na interface e nos endpoints;
- grupos padrão **Administrador**, **Vendedor** e **Manutenção**, além de grupos personalizados;
- matriz de permissões por operação, com criação, edição e exclusão de grupos; a sidebar e as rotas refletem as permissões atuais do usuário;
- cadastro de funcionários e clientes PF/PJ;
- categorias e equipamentos com QR Code gerado, baixável e resolvido pelo sistema;
- manuais, documentos, fotos e evidências acessados no próprio equipamento e na manutenção;
- edição e exclusão contextual dos principais cadastros;
- planos preventivos, agendados, pré-locação e pós-locação;
- manutenção organizada em duas áreas: locação (pré/pós) e oficina/revisões (preventivas, agendadas e corretivas), com apenas “Em aberto” e “Concluído” no filtro e nos cartões das OS;
- OS em cartões com uma única ação de abertura; inspeção e mídias ficam dentro da OS, e planos periódicos permanecem acessíveis na oficina;
- OS em uma tela, com identificação fixa, técnico e avaliação operante/inoperante; etapa, prioridade e agendamento fora do formulário de atendimento, com conclusão pela ação “Concluir e liberar”;
- mídias acessadas pela coluna do equipamento, com prévia local de imagens e PDFs no modal e download para formatos sem prévia;
- histórico de etapas anteriores preservado, com apresentação simplificada das OS atuais;
- ordens preventivas/corretivas, técnico, atividades e liberação técnica;
- orçamento de locação por cliente, período e múltiplos equipamentos;
- transporte opcional de entrega e/ou coleta, com endereço compartilhado por padrão, CEP, complemento e soma automática dos custos de cada trajeto;
- cadastro de veículos e planejamento de viagens com motorista, horário, status e histórico protegido;
- painel de transporte por programação, com uma ação principal por viagem e motivo de bloqueio; entregas aguardam liberação da Manutenção, mas podem ser planejadas antes;
- fluxo integrado: a aprovação cria a entrega; sua confirmação inicia a locação e cria a coleta contratada; receber a coleta no depósito registra a devolução e abre as OS finais, respeitando as permissões de cada operação;
- rascunhos não reservam equipamentos nem criam OS ou viagens; condições comerciais e observações internas saíram do editor, sem apagar os registros históricos;
- disponibilidade validada antes da seleção, com motivo dos bloqueios por equipamento;
- próxima ação e motivo de bloqueio visíveis em cada locação, com destaque no fluxo operacional;
- intervalo operacional configurável por equipamento entre locações, para limpeza, transporte ou preparo;
- registro explícito de procura não atendida quando um equipamento estiver indisponível;
- cálculo automático de diárias, preço negociado por item, desconto e total;
- orçamento PDF versionado e comprovantes operacionais de entrega/devolução, preservando o conteúdo gerado em cada versão;
- bloqueio de sobreposição quando o orçamento vira reserva aprovada;
- bloqueio por OS aberta ou manutenção crítica vencida;
- reserva com responsável, condições e cancelamento auditável;
- OS pré-locação automática na Manutenção para cada equipamento reservado, com detalhes do equipamento e decisão operante/inoperante; equipamentos inoperantes bloqueiam a entrega até o reparo;
- entrega vinculada à inspeção, prorrogação com nova consulta de disponibilidade e histórico;
- devolução com OS de inspeção final aberta na Manutenção para cada equipamento; Locações acompanha o progresso e conclui a devolução;
- encaminhamento de avarias para reparo na mesma OS pós-locação, mantendo o equipamento bloqueado;
- planos de manutenção controlados por data, periodicidade e horas de uso, com OS preventiva agendada gerada automaticamente quando vence o intervalo em dias;
- visão geral com sugestão explicável de compra ou substituição baseada em solicitações, procura não atendida, ocupação, custo de manutenção e preço de aquisição; listas e modais responsivos;
- dados demonstrativos e testes automatizados.
- preparação fiscal genérica com cadastro vazio do emitente, dados fiscais complementares de clientes/equipamentos, conferência por locação e exportação de prévia JSON; acesso controlado por ACL;

Emissão fiscal **real**, cobrança, portal externo, IoT e decisões automáticas por IA continuam fora desta etapa. A sugestão de compra é um sinal estatístico simples, sem modelo externo, cotação de fornecedores ou decisão automática. Os PDFs de orçamento e comprovantes são documentos comerciais/operacionais **não fiscais e sem assinatura**. A área Fiscal prepara cadastros e uma prévia de integração; ainda não calcula tributos nem transmite documentos. O emissor e o enquadramento fiscal serão definidos para a empresa que adotar o sistema.

## Estrutura

```text
PANDORA/
├── api/                    # Django REST API
│   ├── accounts/           # usuários, perfis e autenticação
│   ├── customers/          # clientes PF/PJ
│   ├── assets/             # categorias, equipamentos e mídias
│   ├── maintenance/        # planos, OS e padrões criacionais
│   ├── rentals/            # orçamentos, itens e disponibilidade
│   ├── logistics/          # veículos e viagens opcionais da locação
│   ├── fiscal/             # emitente configurável e preparação dos dados para emissão
│   ├── core/               # dashboard, auditoria e configuração de IA
│   └── config/             # settings e roteamento
├── frontend/               # Vue 3 + Vite
├── docs/                   # arquitetura e contrato da API
└── ARTEFATOS DO PROJETO/   # requisitos e modelagens acadêmicas
```

## Como executar

### 1. Backend

Crie o banco e o usuário no PostgreSQL ou, se utilizar Docker, copie `.env.compose.example` para `.env` na raiz e execute:

```powershell
docker compose up -d postgres
```

Depois, no PowerShell, a partir da pasta `api`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Para reproduzir a base fictícia mais completa desta entrega, use `python manage.py seed_realistic_demo` no lugar de `seed_demo`. O comando exige PostgreSQL `pandora_db` local em modo de desenvolvimento; cria clientes, equipamentos com fotos, veículos, usuários, locações em várias etapas, inspeções, OS, planos de revisão e notificações. É idempotente para os registros demonstrativos, mas **não limpa dados existentes**. Faça backup antes de executar `flush` em uma base que já contenha dados.

A API ficará em `http://127.0.0.1:8000/api/`.

O `.env.example` já usa PostgreSQL. Informe `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e `DB_PORT`. Para um teste temporário sem PostgreSQL, defina explicitamente `DB_ENGINE=sqlite`.

### Revisões periódicas

Em **Manutenção → Oficina e revisões → Revisões automáticas**, escolha o equipamento e o intervalo em dias. O nome é preenchido automaticamente se não for informado; alertas, criticidade e horas de uso ficam em ajustes opcionais. Sem data informada, o primeiro vencimento ocorre X dias após o cadastro (ou após a última manutenção, se registrada). Uma data de próxima execução pode antecipar o primeiro ciclo. Ao vencer, o sistema cria uma única OS **Preventiva · Agendada** vinculada ao plano; ela aparece na oficina e bloqueia a disponibilidade do equipamento até ser concluída ou cancelada. Ao concluir a OS, o próximo vencimento é calculado a partir da data da conclusão. A consulta da tela sincroniza planos vencidos e não duplica OS.

Na OS da oficina, a condição do equipamento fica na mesma tela dos dados do atendimento. Uma falha confirmada exige descrição e mantém o chamado em atendimento. “Salvar avaliação” preserva a etapa e o planejamento; a ação explícita “Concluir e liberar” exige condição operante, técnico, testes finais e permissão de liberação. Valores históricos de peças/horas/custos permanecem no banco, sem campos para alterá-los nessa tela. O código interno `BROKEN` permanece compatível com os registros existentes; o rótulo apresentado é “Inoperante”.

Para gerar OS mesmo sem ninguém abrir o sistema, agende a execução diária deste comando no servidor (Agendador de Tarefas do Windows ou cron):

```powershell
python manage.py generate_preventive_orders
```

### Consulta de endereço e simulação de frete

No orçamento, o botão **Buscar CEP** consulta a [BrasilAPI CEP V2](https://brasilapi.com.br/docs) sob demanda, preenche o endereço e sugere um frete por trecho. O cálculo usa coordenadas aproximadas do CEP, distância em linha reta ajustada por `FREIGHT_ROAD_FACTOR`, `FREIGHT_RATE_PER_KM` e `FREIGHT_MINIMUM_PER_LEG`. Entrega e coleta são cobradas como trechos separados. Não é uma rota viária nem uma tarifa oficial: o vendedor pode corrigir o valor antes de salvar.

Configure `FREIGHT_ORIGIN_CEP` com o CEP real do depósito e ajuste as tarifas no `.env` da API antes de utilizar os valores comercialmente. Enquanto não configurado, a origem **provisória** é o Centro de Leme/SP; se a consulta não devolver coordenadas, o frete fica para preenchimento manual. O desconto do orçamento é informado em percentual sobre equipamentos **mais transporte**, e o valor em reais calculado é persistido para manter compatibilidade com as demais telas.

### 2. Frontend

Em outro terminal, a partir da pasta `frontend`:

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

Também é possível usar `npm install` e `npm run dev`. A aplicação ficará em `http://127.0.0.1:5173`.

### Acesso demonstrativo

| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | `admin@pandora.local` | `Pandora@123` |
| Vendedor | `vendas@pandora.local` | `Pandora@123` |
| Manutenção | `manutencao@pandora.local` | `Pandora@123` |
| Logística | `logistica@pandora.local` | `Pandora@123` |

As credenciais acima são somente para desenvolvimento. Troque-as em qualquer ambiente compartilhado.

O sino do cabeçalho mostra notificações individuais de novas OS, reservas/devoluções e viagens. O contador é atualizado automaticamente a cada 30 segundos; é possível abrir o registro relacionado ou marcar tudo como lido. A API mantém o histórico em `/api/notifications/` e não expõe notificações de outros usuários.

O backup local demonstrativo fica em `backups/PANDORA-demo-completo-2026-10-08-final.zip`: inclui o dump PostgreSQL, as fotos em `media/` e instruções de restauração. `backups/` é ignorado pelo Git para não publicar dados ou cópias de banco acidentalmente.

## Qualidade

```powershell
# API
cd api
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test

# Frontend
cd ..\frontend
pnpm build
```

Consulte [Arquitetura](docs/ARCHITECTURE.md) e [Contrato inicial da API](docs/API.md) para decisões de domínio, regras e endpoints.
Para configurar a preparação fiscal e planejar a integração de emissão, consulte [Preparação fiscal](docs/FISCAL_READINESS.md).

Após atualizar uma instalação existente, execute `python manage.py migrate`. A interface consulta as permissões atuais do usuário ao navegar, sem exigir novo login após ajustes de ACL.

Os fluxos de locação implementam os cards [#37](https://github.com/Felipe-Parolin/PANDORA/issues/37), [#38](https://github.com/Felipe-Parolin/PANDORA/issues/38), [#39](https://github.com/Felipe-Parolin/PANDORA/issues/39), [#40](https://github.com/Felipe-Parolin/PANDORA/issues/40) e [#41](https://github.com/Felipe-Parolin/PANDORA/issues/41).

## Equipe

- 116758 - Eduardo Souza Gomes (Engenheiro de IA e Dados)
- 116276 - Felipe Antonio Parolin (QA / Scrum Master)
- 116849 - Gabriel Eduardo da Cunha (Product Owner & Business Analyst)
- 116743 - Gabriel Moi Stensen (Arquiteto de Software & DBA)
- 117224 - Matheus Henrique Araujo Silva (Desenvolvedor Front-end & UX)
- 116305 - Rafael Donizete Mantoan (Desenvolvedor Back-end / IA)
