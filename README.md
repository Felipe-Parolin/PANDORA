<div align="center">

# PANDORA

**Gestão de locações, manutenção e logística de equipamentos**

Projeto Interdisciplinar · Sistemas de Informação · 2026

</div>

## Sobre o projeto

O PANDORA organiza a operação dos equipamentos da Mazzi Materiais de Construção: cadastros, orçamentos, reservas, inspeções, retiradas e devoluções, manutenção, transporte e contas a receber. O assistente de IA consulta manuais e apoia o técnico; as decisões e liberações continuam sendo humanas.

O projeto usa **Django REST**, **Vue 3** e **PostgreSQL**. Os comandos abaixo são para **PowerShell no Windows**, executados a partir da pasta indicada. Não é necessário ativar o ambiente virtual.

## O que instalar

- **Python 3.12 ou superior**, compatível com Django 6.
- **Node.js 22.12 ou superior** — o projeto também aceita a linha 20 a partir da versão 20.19.
- **PostgreSQL 17 ou 18**, incluindo pgAdmin e as ferramentas de linha de comando.

Confira a instalação no terminal:

```powershell
python --version
node --version
```

Mantenha os arquivos em UTF-8. No VS Code, a codificação aparece no canto inferior direito.

## Como rodar o projeto

### 1. Baixar e abrir

Neste repositório, clique em **Code → Download ZIP** e extraia os arquivos, ou use sua cópia Git. Abra no VS Code a pasta que contém `api`, `frontend` e este README.

### 2. Criar o banco no pgAdmin

1. Abra o pgAdmin e conecte-se ao PostgreSQL instalado.
2. Clique com o botão direito em **Databases → Create → Database**.
3. Em **Database**, informe `pandora_db`.
4. Em **Owner**, escolha seu usuário local do PostgreSQL, normalmente `postgres`.
5. Clique em **Save**. Guarde o nome do usuário e a senha que você definiu na instalação.

### 3. Instalar e configurar o backend

No terminal da raiz do projeto:

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Abra `api/.env` e configure os campos abaixo com os dados do seu PostgreSQL. **Não altere a senha no `settings.py`.**

```dotenv
DB_ENGINE=postgresql
DB_NAME=pandora_db
DB_USER=postgres
DB_PASSWORD=preencha_com_a_senha_do_seu_postgresql
DB_HOST=localhost
DB_PORT=5432
DJANGO_DEBUG=true
AI_ENABLED=false
```

O valor de `DB_PASSWORD` acima é apenas uma indicação de preenchimento. Gere também uma chave exclusiva para `DJANGO_SECRET_KEY` com o comando abaixo e cole o resultado somente em `api/.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Não publique seu `.env`. O `.env.example` já deixa a IA desativada e os e-mails no console para os primeiros testes.

Crie as tabelas:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

### 4. Carregar a base de testes

Ainda na pasta `api`:

```powershell
.\.venv\Scripts\python.exe manage.py seed_realistic_demo
```

Na primeira execução, o comando solicita uma senha para os **novos usuários de demonstração**, sem mostrá-la no terminal. Anote a senha que você escolher. Usuários existentes mantêm sua senha, grupo e dados; reexecutar a carga não apaga a base nem desfaz os testes já feitos.

| Acesso | E-mail |
| --- | --- |
| Administrador | `admin@pandora.local` |
| Vendas | `vendas@pandora.local` |
| Manutenção | `manutencao@pandora.local` |
| Logística | `logistica@pandora.local` |
| Somente consulta financeira | `consulta@pandora.local` |

A carga cria dados fictícios com datas relativas ao dia da execução. Ela prepara fotos, manuais, histórico técnico, notificações, locações em diferentes etapas, viagens, campanhas em rascunho, contas abertas e recibos de baixas. Não envia e-mails nem consulta IA ou mapas. É permitida somente no PostgreSQL local `pandora_db` em desenvolvimento e em bancos locais de testes com prefixo `test_`.

Caso precise redefinir uma senha **na sua instalação local**:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword admin@pandora.local
```

### 5. Iniciar a API

No mesmo terminal, ainda em `api`:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Mantenha esse terminal aberto. A API estará em **http://127.0.0.1:8000/api/**.

### 6. Iniciar o site

Abra **outro terminal na raiz do projeto**:

```powershell
cd frontend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm.cmd install
npm.cmd run dev
```

Abra **http://127.0.0.1:5173** e entre com um dos acessos acima e a senha definida na carga. Se o Vite indicar outra porta, use o endereço mostrado no terminal e ajuste `CORS_ALLOWED_ORIGINS` em `api/.env`.

**Para iniciar novamente:** execute apenas os comandos `runserver` e `npm.cmd run dev`, cada um em seu terminal. Depois de atualizar o código, rode `migrate` e instale novamente as dependências se os arquivos de requisitos mudaram.

No Linux/macOS, substitua `python` por `python3` na criação do ambiente, `.venv\Scripts\python.exe` por `.venv/bin/python` e `npm.cmd` por `npm`.

## O que testar na base demonstrativa

| Área | Sugestões de teste |
| --- | --- |
| Cadastros | Clientes PF/PJ, documentos e máscaras, endereços com número separado, observações, usuários, permissões, categorias e checklists, equipamentos e veículos. |
| Locações | Orçamento em etapas, edição, disponibilidade, aprovação, inspeção prévia, entrega e devolução parcial, períodos e endereços por equipamento, prorrogação, cancelamento e PDFs. |
| Manutenção | OS pré/pós-locação, reparo de avaria no retorno, chamados abertos/em execução/aguardando peças/abandonados, revisão periódica e liberação técnica. |
| Logística | Entregas e coletas, agenda, viagem em andamento, veículo/motorista, roteiro do dia e carga. Os pontos demonstrativos do mapa são ilustrativos. |
| Comercial | Faturamento, contas por cliente, mudança de vencimento, juros após cinco dias de carência, seleção de várias contas, baixa, recibo PDF, sugestões de compra e campanhas. |
| Assistente | Manuais PDF indexados, histórico de casos e consultas fictícias identificadas como demonstração. Para respostas de um modelo real, configure a IA abaixo. |

Comece pelas locações `ORC-CEN-007` (três equipamentos, períodos/destinos e entrega parcial), `ORC-CEN-008` (devolução parcial), `ORC-CEN-009` (transporte em andamento) e `ORC-CEN-010` (avaria na devolução). Em Contas a receber, procure **Construtora Vila Nova Ltda** para testar seleção entre páginas e contas baixadas.

As contas são geradas na primeira entrega, vencendo na devolução prevista. A taxa inicial é **1% ao mês, simples**, proporcional por dia após cinco dias de carência, editável na conta aberta. A baixa registra o pagamento informado pelo operador; não movimenta dinheiro nem emite nota fiscal.

### IA, frete e e-mail

- **IA real:** em `api/.env`, preencha sua própria `GROQ_API_KEY`, altere `AI_ENABLED=true` e reinicie a API. Sem isso, o restante do sistema funciona e a consulta aos manuais pode usar a busca local.
- **Frete e mapa:** precisam de internet. O depósito já está configurado. Use um endereço real com CEP e número para testar uma rota; endereços da carga são fictícios. Entrega e coleta são calculadas separadamente. A tarifa inicial é R$ 3,00/km, com mínimo de R$ 25,00 por trecho/viagem, além dos adicionais configurados.
- **E-mail de marketing sem envio real:** para testar a preparação e o botão de envio, use as configurações abaixo e reinicie a API. A mensagem será escrita apenas no terminal. As campanhas da carga permanecem em rascunho até sua ação.

```dotenv
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=localhost
DEFAULT_FROM_EMAIL=teste@example.invalid
```

## Como criar um backup para os demais testadores

### 1. Preparar a base

Use apenas dados fictícios. Feche o site e pare o `runserver` com **Ctrl+C** enquanto gera a cópia, para evitar alterações durante o backup.

### 2. Gerar o arquivo

Em um terminal **na raiz do projeto**:

```powershell
.\api\.venv\Scripts\python.exe api/manage.py backup_local
```

O comando lê a conexão configurada, localiza `pg_dump`, exporta o PostgreSQL e cria um ZIP em `backups/`. O arquivo contém:

- `database.dump`: banco completo, incluindo usuários, permissões e histórico;
- `media/`: fotos, manuais e evidências;
- `manifest.json`: data e hashes para verificar a integridade dos arquivos.

O dump e o ZIP são verificados antes da conclusão. `.env`, chaves e configurações pessoais não entram no arquivo. O backup contém os dados e hashes de senha dos usuários: compartilhe somente a base fictícia, por um canal da equipe. A pasta `backups` é ignorada pelo Git.

Se as ferramentas do PostgreSQL não forem encontradas, informe o caminho da versão instalada, por exemplo:

```powershell
.\api\.venv\Scripts\python.exe api/manage.py backup_local --pg-dump "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
```

### 3. Restaurar em outro computador

1. Instale a mesma versão principal do PostgreSQL usada na origem e configure o projeto até instalar as dependências.
2. Extraia o ZIP recebido em uma pasta temporária.
3. No pgAdmin, crie um banco **vazio**, por exemplo `pandora_db_restaurado`. Não execute `migrate` nesse banco antes da restauração.
4. Clique com o botão direito no novo banco → **Restore**. Selecione `database.dump`, mantenha o formato **Custom** e execute a restauração. Confira o registro da operação.
5. Copie a pasta `media` extraída para `api/media`.
6. Em `api/.env`, ajuste `DB_NAME` para o banco restaurado e informe seu próprio usuário e senha do PostgreSQL.
7. Rode `.\api\.venv\Scripts\python.exe api/manage.py migrate` a partir da raiz. Isso aplica eventuais migrações posteriores ao backup.
8. Se não conhecer a senha do acesso demonstrativo, redefina-a localmente com `.\api\.venv\Scripts\python.exe api/manage.py changepassword admin@pandora.local`.
9. Inicie a API e o frontend conforme os passos anteriores.

Para reproduzir os cenários sem receber um ZIP, basta executar a carga `seed_realistic_demo` em um banco local novo. O código dessa carga acompanha o repositório.

## Testes automatizados

Na raiz do projeto, com PostgreSQL disponível:

```powershell
$env:AI_ENABLED='false'
.\api\.venv\Scripts\python.exe api/manage.py check
.\api\.venv\Scripts\python.exe api/manage.py test accounts assets commercial core customers rentals maintenance logistics --keepdb --noinput
cd frontend
npm.cmd test
npm.cmd run build
```

O Django usa um banco separado com prefixo `test_`. O usuário do PostgreSQL precisa ter permissão para criá-lo. O comando acima cobre os módulos operacionais e comerciais; testes específicos de IA ficam em `api/ai`. A carga não substitui testes automatizados.

## Estrutura e equipe

`api/` contém a API, migrações e comandos de gestão; `frontend/` contém o site; `ARTEFATOS DO PROJETO/` reúne os materiais acadêmicos. `api/media/`, `backups/` e arquivos `.env` são locais.

| RA | Nome |
| --- | --- |
| 116758 | Eduardo Souza Gomes |
| 116276 | Felipe Antonio Parolin |
| 116849 | Gabriel Eduardo da Cunha |
| 116743 | Gabriel Moi Stensen |
| 117224 | Matheus Henrique Araujo Silva |
| 116305 | Rafael Donizete Mantoan |
