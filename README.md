# PANDORA

Plataforma interna para locação, inspeção e manutenção dos equipamentos próprios da Mazzi Materiais de Construção.

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
- manutenção organizada em duas áreas: locação (pré/pós) e oficina/revisões (preventivas, agendadas e corretivas), com etapa operacional como filtro;
- OS em cartões com uma única ação de abertura; inspeção e mídias ficam dentro da OS, e planos periódicos permanecem acessíveis na oficina;
- abandono de chamado com justificativa obrigatória, datas de transição e redistribuição visível;
- ordens preventivas/corretivas, técnico, atividades e liberação técnica;
- orçamento de locação por cliente, período e múltiplos equipamentos;
- transporte opcional de entrega e/ou coleta, com CEP, endereço, complemento e valor discriminado no orçamento;
- cadastro de veículos e planejamento de viagens com motorista, horário, status e histórico protegido;
- fluxo integrado: ao aprovar a reserva com entrega, a viagem aparece em Transporte; a liberação técnica precede a viagem; viagem concluída precede a entrega ou devolução quando o transporte é contratado;
- disponibilidade validada antes da seleção, com motivo dos bloqueios por equipamento;
- cálculo automático de diárias, preço negociado por item, desconto e total;
- bloqueio de sobreposição quando o orçamento vira reserva aprovada;
- bloqueio por OS aberta ou manutenção crítica vencida;
- reserva com responsável, condições e cancelamento auditável;
- OS pré-locação automática na Manutenção para cada equipamento reservado, com checklist por categoria, fotos, observações e impedimento crítico;
- entrega vinculada à inspeção, prorrogação com nova consulta de disponibilidade e histórico;
- devolução com OS de inspeção final aberta na Manutenção para cada equipamento; Locações acompanha o progresso e conclui a devolução;
- encaminhamento de avarias para reparo na mesma OS pós-locação, mantendo o equipamento bloqueado;
- planos de manutenção controlados por data, periodicidade e horas de uso, com OS preventiva agendada gerada automaticamente quando vence o intervalo em dias;
- dashboard, listas em cartões e modais responsivos para desktop e celular;
- dados demonstrativos e testes automatizados.

Emissão fiscal **real**, cobrança, portal externo, IoT e decisões automáticas por IA continuam fora desta etapa. A operação de locação não gera nota fiscal nem documento fiscal de transporte. A integração fiscal exigirá validação com a contabilidade da empresa antes de configurar regime, inscrição e documentos aplicáveis em Leme/SP.

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

Em **Manutenção → Oficina e revisões → Planos de revisão periódica**, cadastre o equipamento e o intervalo em dias. Sem data informada, o primeiro vencimento ocorre X dias após o cadastro (ou após a última manutenção, se registrada). Uma data de próxima execução pode antecipar o primeiro ciclo. Ao vencer, o sistema cria uma única OS **Preventiva · Agendada** vinculada ao plano; ela aparece na oficina e bloqueia a disponibilidade do equipamento até ser concluída ou cancelada. Ao concluir a OS, o próximo vencimento é calculado a partir da data da conclusão. A consulta da tela sincroniza planos vencidos e não duplica OS.

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
Para a emissão fiscal futura em Leme/SP, consulte [Preparação fiscal](docs/FISCAL_READINESS.md).

Após atualizar uma instalação existente, execute `python manage.py migrate`. A interface consulta as permissões atuais do usuário ao navegar, sem exigir novo login após ajustes de ACL.

Os fluxos de locação implementam os cards [#37](https://github.com/Felipe-Parolin/PANDORA/issues/37), [#38](https://github.com/Felipe-Parolin/PANDORA/issues/38), [#39](https://github.com/Felipe-Parolin/PANDORA/issues/39), [#40](https://github.com/Felipe-Parolin/PANDORA/issues/40) e [#41](https://github.com/Felipe-Parolin/PANDORA/issues/41).

## Equipe

- 116758 - Eduardo Souza Gomes (Engenheiro de IA e Dados)
- 116276 - Felipe Antonio Parolin (QA / Scrum Master)
- 116849 - Gabriel Eduardo da Cunha (Product Owner & Business Analyst)
- 116743 - Gabriel Moi Stensen (Arquiteto de Software & DBA)
- 117224 - Matheus Henrique Araujo Silva (Desenvolvedor Front-end & UX)
- 116305 - Rafael Donizete Mantoan (Desenvolvedor Back-end / IA)
