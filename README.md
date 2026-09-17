# PANDORA

Plataforma interna para locação, inspeção e manutenção dos equipamentos próprios da Mazzi Materiais de Construção.

Este repositório contém a primeira versão funcional do MVP: API em Python/Django REST, frontend em Vue 3 e PostgreSQL 17 como banco principal. O SQLite permanece apenas como opção explícita para testes isolados.

## O que já está implementado

- autenticação JWT com ACL aplicada na interface e nos endpoints;
- grupos padrão **Administrador**, **Vendedor** e **Manutenção**, além de grupos personalizados;
- matriz de permissões por operação, com criação, edição e exclusão de grupos;
- cadastro de funcionários e clientes PF/PJ;
- categorias e equipamentos com QR Code gerado, baixável e resolvido pelo sistema;
- manuais, documentos, fotos e evidências acessados no próprio equipamento e na manutenção;
- edição e exclusão contextual dos principais cadastros;
- planos preventivos, agendados, pré-locação e pós-locação;
- chamados de manutenção em filas operacionais: sem técnico, aguardando início, em andamento, aguardando peças, abandonados e concluídos;
- abandono de chamado com justificativa obrigatória, datas de transição e redistribuição visível;
- ordens preventivas/corretivas, técnico, atividades e liberação técnica;
- orçamento de locação por cliente, período e múltiplos equipamentos;
- disponibilidade validada antes da seleção, com motivo dos bloqueios por equipamento;
- cálculo automático de diárias, preço negociado por item, desconto e total;
- bloqueio de sobreposição quando o orçamento vira reserva aprovada;
- bloqueio por OS aberta ou manutenção crítica vencida;
- dashboard, listas em cartões e modais responsivos para desktop e celular;
- dados demonstrativos e testes automatizados.

Emissão fiscal, cobrança, portal externo, IoT e decisões automáticas por IA continuam fora desta etapa, em conformidade com o Plano de Escopo.

## Estrutura

```text
PANDORA/
├── api/                    # Django REST API
│   ├── accounts/           # usuários, perfis e autenticação
│   ├── customers/          # clientes PF/PJ
│   ├── assets/             # categorias, equipamentos e mídias
│   ├── maintenance/        # planos, OS e padrões criacionais
│   ├── rentals/            # orçamentos, itens e disponibilidade
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

A API ficará em `http://127.0.0.1:8000/api/`.

O `.env.example` já usa PostgreSQL. Informe `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e `DB_PORT`. Para um teste temporário sem PostgreSQL, defina explicitamente `DB_ENGINE=sqlite`.

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

As credenciais acima são somente para desenvolvimento. Troque-as em qualquer ambiente compartilhado.

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

## Equipe

- 116758 - Eduardo Souza Gomes (Engenheiro de IA e Dados)
- 116276 - Felipe Antonio Parolin (QA / Scrum Master)
- 116849 - Gabriel Eduardo da Cunha (Product Owner & Business Analyst)
- 116743 - Gabriel Moi Stensen (Arquiteto de Software & DBA)
- 117224 - Matheus Henrique Araujo Silva (Desenvolvedor Front-end & UX)
- 116305 - Rafael Donizete Mantoan (Desenvolvedor Back-end / IA)
