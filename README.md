<div align="center">

<img src="docs/assets/readme-banner.svg" alt="PANDORA — Gestão de locações, manutenção e logística de equipamentos. Projeto Interdisciplinar de Sistemas de Informação, 2026." width="100%">

**Django REST · Vue 3 · PostgreSQL**

Da reserva à devolução: equipamentos, pessoas e processos conectados.

[Conheça o projeto](#sobre-o-projeto) · [Instale e execute](#primeira-instalação) · [Explore os dados](#o-que-testar) · [Resolva dúvidas](#dúvidas-frequentes)

</div>

---

## Sobre o projeto

O **PANDORA** organiza a operação de equipamentos da Mazzi Materiais de Construção, reunindo cadastros, orçamentos, reservas, inspeções, retiradas, devoluções, manutenção, transporte e contas a receber.

O assistente de IA consulta manuais e apoia o trabalho técnico. As decisões e liberações continuam sob responsabilidade das pessoas que operam o sistema.

**Vai testar pela primeira vez?** Siga as seis etapas abaixo. A base de demonstração acompanha o repositório e inclui clientes, equipamentos com fotos e operações em diferentes situações, para que você possa explorar o sistema desde o primeiro acesso.

## Antes de começar

Instale as ferramentas abaixo no seu computador:

| Ferramenta | Versão | Para que será utilizada |
| --- | --- | --- |
| Python | 3.12 ou superior, compatível com Django 6 | Executar a API do projeto. |
| Node.js | 22.12 ou superior; também aceita a linha 20 a partir da 20.19 | Instalar as dependências e executar o site. |
| PostgreSQL | 17 ou 18, com pgAdmin | Armazenar e consultar os dados. |

Confira as instalações de Python e Node.js em um terminal:

```powershell
python --version
node --version
```

Este guia utiliza **PowerShell no Windows**. Os comandos indicam em qual pasta você deve estar. Mantenha os arquivos em **UTF-8**; no VS Code, a codificação aparece no canto inferior direito.

> **Em Linux ou macOS:** utilize `python3` quando necessário e substitua `.\.venv\Scripts\Activate.ps1` por `source .venv/bin/activate`.

## Primeira instalação

### 1. Baixe e abra o projeto

No GitHub, clique em **Code → Download ZIP** e extraia os arquivos, ou utilize sua cópia Git. Abra no VS Code a pasta que contém `api`, `frontend` e este README. Essa será a **raiz do projeto** nos próximos passos.

### 2. Crie seu banco de dados

No pgAdmin:

1. Conecte-se ao PostgreSQL instalado no seu computador.
2. Clique com o botão direito em **Databases → Create → Database**.
3. No campo **Database**, informe `pandora_db`.
4. Em **Owner**, selecione seu usuário local do PostgreSQL, normalmente `postgres`.
5. Clique em **Save**.

Tenha à mão o usuário e a senha definidos na instalação do PostgreSQL. Você vai utilizá-los na configuração da próxima etapa.

### 3. Prepare a API

A API, também chamada de backend, processa as operações do sistema e se conecta ao banco de dados.

**No terminal da raiz do projeto**, crie e ative um ambiente virtual para manter as dependências do Python separadas das demais instalações do computador:

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

O último comando cria seu arquivo de configuração local sem substituir um `.env` existente.

Abra **`api/.env`** e ajuste os campos abaixo para o banco que você acabou de criar:

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

Substitua `DB_PASSWORD` pela sua senha e ajuste `DB_USER` se utilizar outro usuário. As credenciais do banco devem ser configuradas nesse arquivo; não é necessário editar `settings.py`.

**Ainda no mesmo terminal**, gere uma chave exclusiva para o Django:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copie o resultado para o campo `DJANGO_SECRET_KEY` em `api/.env` e salve o arquivo.

> **Configuração pessoal:** mantenha senhas e chaves somente no `.env` local. Esse arquivo é ignorado pelo Git. O `.env.example` deve continuar sem credenciais reais.

Os demais valores do arquivo de exemplo já permitem iniciar os testes locais: a IA fica desativada e os e-mails aparecem apenas no terminal. Veja [Configurações opcionais](#configurações-opcionais) quando precisar ajustar integrações ou endereços.

### 4. Carregue a base de demonstração

Com o ambiente virtual ativo, **na pasta `api`**, execute:

```powershell
python manage.py migrate
python manage.py seed_realistic_demo
```

O primeiro comando cria as tabelas no seu banco. O segundo preenche essas tabelas com os dados fictícios que acompanham o projeto no GitHub. Não é necessário receber um backup de outra pessoa.

Quando solicitado, **defina e confirme uma senha com pelo menos 8 caracteres**. A digitação fica oculta no terminal. Essa será a senha dos novos usuários demonstrativos:

| Perfil | E-mail para entrar |
| --- | --- |
| Administrador | `admin@pandora.local` |
| Vendas | `vendas@pandora.local` |
| Manutenção | `manutencao@pandora.local` |
| Logística | `logistica@pandora.local` |
| Consulta financeira | `consulta@pandora.local` |

Aguarde a mensagem **Base fictícia pronta**, acompanhada do resumo dos registros. O acesso de administrador já estará disponível para testar pelo site, sem precisar executar `createsuperuser`.

**O que você encontrará em um banco novo:**

| Clientes | Categorias | Equipamentos com fotos | Veículos | Orçamentos e locações |
| :---: | :---: | :---: | :---: | :---: |
| 18 | 12 | 30 | 12 | 26 |

A carga também prepara inspeções, ordens de serviço, planos de manutenção, contas a receber, pagamentos fictícios, recibos, 12 campanhas em rascunho, manuais PDF e histórico demonstrativo de IA.

As datas dos cenários são calculadas na primeira carga. Fotos e manuais são gravados automaticamente em `api/media/`. O carregamento não envia e-mails nem consulta serviços externos de IA ou mapas.

> **Banco de demonstração:** utilize uma base dedicada aos testes. O comando exige PostgreSQL local (`localhost`, `127.0.0.1` ou `::1`), `DJANGO_DEBUG=true` e banco chamado `pandora_db` ou com prefixo `test_`.

Você não precisa repetir a carga a cada inicialização. Reexecutá-la não limpa o banco nem reinicia os cenários, e os usuários existentes mantêm suas senhas e permissões. Evite executar o comando antigo `seed_demo`, pois ele redefine os acessos demonstrativos.

### 5. Inicie a API

**No mesmo terminal, na pasta `api`:**

```powershell
python manage.py runserver
```

Mantenha esse terminal aberto enquanto utiliza o sistema. A API estará disponível em **http://127.0.0.1:8000/api/**.

### 6. Inicie o site e faça seu primeiro acesso

Abra **outro terminal na raiz do projeto** e execute:

```powershell
cd frontend
npm install
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm run dev
```

Acesse **http://127.0.0.1:5173** e entre com um dos e-mails demonstrativos e a senha que você definiu na etapa 4. Para conhecer todas as áreas, comece pelo perfil **Administrador**.

Se o Vite indicar outra porta, abra o endereço mostrado no terminal e ajuste as configurações de endereço descritas em [Configurações opcionais](#configurações-opcionais).

## Como iniciar nas próximas vezes

Depois da primeira instalação, basta abrir **dois terminais na raiz do projeto**.

**Terminal 1 — API:**

```powershell
cd api
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

**Terminal 2 — site:**

```powershell
cd frontend
npm run dev
```

Mantenha ambos abertos durante o uso. Para encerrar cada processo, pressione **Ctrl+C** no respectivo terminal.

Não é necessário recriar o ambiente virtual, reinstalar as dependências ou carregar os dados novamente a cada uso. Depois de atualizar o código, execute `python manage.py migrate` na pasta `api`, com o ambiente virtual ativo. Reinstale as dependências apenas quando `api/requirements.txt` ou os arquivos de dependências do frontend forem alterados.

## O que testar

| Área | Sugestões para explorar |
| --- | --- |
| Cadastros | Consulte clientes PF/PJ, categorias, checklists, equipamentos com fotos e veículos. Compare os acessos dos diferentes perfis. |
| Locações | Explore orçamentos, reservas, inspeções, entregas e devoluções parciais, períodos e destinos por equipamento e documentos PDF. |
| Manutenção | Acompanhe OS abertas, agendadas, em execução, aguardando peças, abandonadas e concluídas, além dos planos preventivos. |
| Logística | Consulte entregas e coletas planejadas, concluídas e em andamento, com veículo e motorista. As coordenadas demonstrativas são ilustrativas. |
| Comercial | Teste contas abertas e vencidas, baixas fictícias com recibo, sugestões de compra e campanhas em rascunho. |
| Assistente | Consulte manuais PDF demonstrativos indexados e o histórico fictício de IA. Respostas de um modelo real dependem da configuração opcional. |

**Para começar pelas operações, procure estas locações:**

| Locação | Cenário |
| --- | --- |
| `ORC-CEN-007` | Entrega parcial de uma locação com três equipamentos. |
| `ORC-CEN-008` | Devolução parcial. |
| `ORC-CEN-009` | Transporte em andamento. |
| `ORC-CEN-010` | Avaria identificada na devolução. |

Em **Contas a receber**, procure **Construtora Vila Nova Ltda** para consultar contas abertas e baixadas e testar a seleção entre páginas.

Os dados são fictícios e os pagamentos não movimentam dinheiro. Rotas reais e respostas do provedor de IA dependem das configurações abaixo.

## Configurações opcionais

Os valores de `api/.env.example` e `frontend/.env.example` atendem ao desenvolvimento local. Faça os ajustes no seu `.env` e reinicie o serviço correspondente para aplicá-los.

<details>
<summary><strong>Endereços e portas de acesso</strong></summary>

Se o site iniciar em outra porta ou se você acessar o sistema por outro dispositivo, confira os endereços permitidos em `api/.env`:

- `DJANGO_ALLOWED_HOSTS`: nomes ou IPs pelos quais a API será acessada.
- `CORS_ALLOWED_ORIGINS`: origens autorizadas do site, incluindo protocolo e porta.
- `FRONTEND_URL`: endereço do site.
- `BACKEND_PUBLIC_URL`: endereço público da API, sem o sufixo `/api/`.

Em `frontend/.env`, confira também `VITE_API_BASE_URL`, que aponta para a API e inclui `/api/`. Para os endereços deste guia, o valor é `http://127.0.0.1:8000/api`.

</details>

<details>
<summary><strong>Assistente de inteligência artificial</strong></summary>

Para habilitar respostas de um modelo real, crie sua chave no [console da Groq](https://console.groq.com/keys), preencha `GROQ_API_KEY` em `api/.env`, altere `AI_ENABLED=true` e reinicie a API.

Mantenha a chave apenas no arquivo local. Sem essa configuração, a integração com o modelo permanece desativada; a base de demonstração já inclui manuais e histórico fictício para exploração.

</details>

<details>
<summary><strong>Frete e mapa</strong></summary>

O arquivo de exemplo já contém CEP, endereço e coordenadas de origem do depósito, tarifa por quilômetro, valor mínimo por trecho e parâmetros de viagem. Confira esses valores antes do uso operacional.

A consulta de endereços e rotas precisa de internet e utiliza os serviços configurados em `GEOCODING_SEARCH_URL` e `FREIGHT_ROUTING_URL`. Para testar uma rota real, informe um endereço com CEP e número; as coordenadas da demonstração são apenas ilustrativas.

</details>

<details>
<summary><strong>E-mails de teste e envio real</strong></summary>

Por padrão, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` mostra as mensagens no terminal da API, sem enviá-las. Você pode explorar a preparação das campanhas nesse modo.

Para enviar mensagens reais, configure um backend SMTP e os dados do seu serviço exclusivamente em `api/.env`. As campanhas demonstrativas permanecem em rascunho até uma ação do usuário.

</details>

## Dúvidas frequentes

<details>
<summary><strong>O PowerShell bloqueou a ativação do ambiente virtual. Como continuar?</strong></summary>

Você pode chamar diretamente o Python do ambiente virtual, sem alterar a política do PowerShell. Na pasta `api`, utilize:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_realistic_demo
.\.venv\Scripts\python.exe manage.py runserver
```

Para os demais comandos Python deste guia, substitua `python` por `.\.venv\Scripts\python.exe`.

Se o PowerShell bloquear `npm.ps1`, utilize `npm.cmd install` e `npm.cmd run dev` na pasta `frontend`.

</details>

<details>
<summary><strong>A API não conseguiu se conectar ao PostgreSQL.</strong></summary>

Confira se o PostgreSQL está em execução e se o banco foi criado no pgAdmin. Verifique `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e `DB_PORT` no arquivo `api/.env` e tente novamente. Utilize as credenciais da sua instalação local.

</details>

<details>
<summary><strong>A carga de demonstração recusou meu banco.</strong></summary>

Confira em `api/.env`: `DB_ENGINE=postgresql`, `DJANGO_DEBUG=true`, `DB_HOST=localhost` e `DB_NAME=pandora_db`. O comando também aceita os hosts `127.0.0.1` e `::1` e nomes de banco com prefixo `test_`. Essa restrição evita executar a carga fora do ambiente local de demonstração.

</details>

<details>
<summary><strong>Esqueci a senha de um acesso demonstrativo.</strong></summary>

Com o ambiente virtual ativo, na pasta `api`, execute:

```powershell
python manage.py changepassword admin@pandora.local
```

Substitua o e-mail se precisar alterar a senha de outro perfil. Reexecutar a carga não altera a senha de usuários existentes.

</details>

<details>
<summary><strong>Quero testar novamente com os cenários originais.</strong></summary>

Crie outro banco vazio no pgAdmin, por exemplo `test_pandora_demo`, e ajuste `DB_NAME` em `api/.env`. Com o ambiente virtual ativo, na pasta `api`, execute:

```powershell
python manage.py migrate
python manage.py seed_realistic_demo
```

Depois, reinicie a API. O banco anterior permanece preservado, com as alterações feitas nos seus testes.

</details>

## Estrutura do projeto

| Caminho | Conteúdo |
| --- | --- |
| `api/` | API Django, migrações e comandos de gestão. |
| `api/accounts/demo_scenarios.py` | Cenários fictícios utilizados na carga demonstrativa. |
| `api/seed_assets/equipment/` | Imagens que acompanham o repositório para os testes. |
| `frontend/` | Interface web em Vue 3. |
| `docs/assets/` | Recursos visuais da documentação. |
| `ARTEFATOS DO PROJETO/` | Materiais acadêmicos do projeto. |

As pastas `api/media/` e `backups/`, assim como os arquivos `.env`, são locais e não acompanham o GitHub.

## Equipe

Projeto Interdisciplinar · Sistemas de Informação · 2026

| RA | Integrante |
| --- | --- |
| 116758 | Eduardo Souza Gomes |
| 116276 | Felipe Antonio Parolin |
| 116849 | Gabriel Eduardo da Cunha |
| 116743 | Gabriel Moi Stensen |
| 117224 | Matheus Henrique Araujo Silva |
| 116305 | Rafael Donizete Mantoan |

---

[Voltar ao início](#sobre-o-projeto)
