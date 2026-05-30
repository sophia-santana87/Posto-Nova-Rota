# Posto Nova Rota - Sistema RotaFacil

Aplicacao web desenvolvida em Flask para apresentar o Posto Nova Rota e gerenciar
clientes empresariais, veiculos, servicos prestados, faturas e boletos.

O projeto possui paginas institucionais responsivas e tres areas protegidas:

- **Administrador:** gerencia clientes, veiculos, servicos, boletos, faturamento,
  acessos e relatorios.
- **Funcionario:** consulta clientes e boletos, acompanha o faturamento e registra
  novos servicos.
- **Cliente:** consulta seus proprios dados, veiculos, servicos e boletos.

Tambem foram implementados formulario de contato, redefinicao demonstrativa de
senha, exportacao de relatorios em CSV/PDF, logs de auditoria e backup automatico.

## 1. Programas Necessarios

Instale estes programas normalmente no Windows antes de executar o projeto:

1. [Python 3](https://www.python.org/downloads/)
   Durante a instalacao, marque a opcao **Add Python to PATH**.
2. [MySQL Community Server](https://dev.mysql.com/downloads/mysql/)
   O servidor local deve estar ativo na porta `3306`.
3. [MySQL Workbench](https://dev.mysql.com/downloads/workbench/)
   Recomendado para criar, importar e consultar o banco MySQL.
4. [Visual Studio Code](https://code.visualstudio.com/)
   Recomendado para abrir e editar o projeto.

## 2. Extensoes Recomendadas Para o VS Code

Abra o VS Code, clique no icone **Extensions** na barra lateral ou pressione
`Ctrl+Shift+X`. Pesquise e instale:

| Extensao | Finalidade |
| --- | --- |
| **Python** - Microsoft | Executar, depurar e editar arquivos Python. |
| **Pylance** - Microsoft | Autocompletar codigo e indicar erros em Python. |
| **SQLTools** | Abrir conexoes e executar comandos SQL pelo VS Code. |
| **SQLTools MySQL/MariaDB/TiDB Driver** | Permitir que o SQLTools conecte ao MySQL. |

O projeto pode ser executado sem **Live Server**. As paginas devem ser abertas
pelo Flask, pois dependem das rotas Python, do Jinja e dos bancos de dados.

## 3. Abrir o Projeto

No VS Code:

1. Clique em **File > Open Folder**.
2. Selecione a pasta `PostoNovaRota`.
3. Abra o terminal integrado com `Ctrl+'`.

Confirme que o Python esta disponivel:

```powershell
python --version
```

## 4. Criar o Ambiente Python

No terminal, dentro da pasta do projeto, crie um ambiente virtual:

```powershell
python -m venv venv
```

Ative o ambiente:

```powershell
.\venv\Scripts\Activate.ps1
```

Se o PowerShell bloquear a ativacao, execute uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Depois instale as dependencias:

```powershell
pip install -r requirements.txt
```

## 5. Configurar o Arquivo `.env`

Crie um arquivo chamado `.env` na raiz do projeto. Esse arquivo guarda
configuracoes locais e nao deve ser enviado para repositorios publicos.

Use este modelo e substitua os valores de exemplo:

```dotenv
SECRET_KEY=troque-por-uma-chave-longa-e-aleatoria

FLASK_ENV=development
FLASK_DEBUG=False
PORT=8001

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=sua-senha-do-mysql
MYSQL_DATABASE=rota_facil

RELATORIOS_DATA_INICIAL=2026-05-30

# O envio de e-mail e opcional durante o desenvolvimento.
MAIL_HOST=
MAIL_PORT=587
MAIL_USER=
MAIL_PASSWORD=
MAIL_SENDER=
MAIL_RECIPIENT=
```

Observacoes:

- `SECRET_KEY` e obrigatoria porque protege sessoes e tokens CSRF.
- `MYSQL_PASSWORD` deve ser a senha criada durante a instalacao do MySQL.
- `RELATORIOS_DATA_INICIAL` define a partir de qual data as movimentacoes
  aparecem nas exportacoes CSV/PDF.
- Se as variaveis `MAIL_*` ficarem vazias, a mensagem de contato ainda sera
  salva localmente, mas nenhum e-mail sera enviado.

## 6. Entender os Bancos de Dados

O sistema utiliza dois bancos com responsabilidades diferentes.

### 6.1. MySQL Principal

O banco MySQL `rota_facil` guarda os dados operacionais:

- clientes;
- enderecos;
- veiculos;
- tipos de servico e precos;
- servicos registrados;
- faturas;
- boletos.

Antes de iniciar o site, importe no MySQL o schema operacional `rota_facil`
elaborado a partir do DER do projeto. Esse dump nao esta incluido neste
repositorio: obtenha a versao atual com a equipe responsavel pelo banco.

Passo a passo no MySQL Workbench:

1. Abra o Workbench e conecte ao servidor local.
2. Importe o dump operacional fornecido pela equipe.
3. Confirme que o schema criado se chama `rota_facil`.
4. Confira se as tabelas aparecem no painel **Schemas**.
5. Atualize `MYSQL_USER`, `MYSQL_PASSWORD` e `MYSQL_DATABASE` no `.env`.
6. Inicie o Flask somente depois de concluir a importacao.

O aplicativo valida a estrutura ao iniciar e espera, no minimo, estas tabelas:

```text
cliente
endereço
veiculo
serviço_utilizado
serviço
fatura
boleto
```

Preserve os nomes exatos definidos no DER, inclusive os acentos.

O arquivo [`database/acessos_mysql.sql`](database/acessos_mysql.sql) documenta
os papeis e permissoes planejados:

- `papel_admin_nova_rota`: acesso total;
- `papel_funcionario_nova_rota`: consultas e operacoes de atendimento;
- `papel_cliente_nova_rota`: somente leitura.

Para desenvolvimento local, o `.env` pode usar o usuario `root`. Em uma
implantacao real, crie um usuario tecnico proprio, conceda somente as permissoes
necessarias e atualize `MYSQL_USER` e `MYSQL_PASSWORD`.

### 6.2. Conectar O SQLTools Ao MySQL

Depois de instalar as extensoes do VS Code:

1. Clique no icone **SQLTools** na barra lateral.
2. Escolha **Add New Connection**.
3. Selecione **MySQL**.
4. Informe servidor `localhost`, porta `3306` e banco `rota_facil`.
5. Preencha o mesmo usuario e a mesma senha configurados no `.env`.
6. Teste e salve a conexao.

O SQLTools facilita consultas manuais, mas nao substitui o servidor MySQL.

### 6.3. SQLite Auxiliar

O arquivo `database/rotafacil.db` e criado e atualizado automaticamente quando
o Flask inicia. Ele guarda:

- usuarios usados no login;
- mensagens recebidas pelo formulario de contato;
- tabelas antigas mantidas para compatibilidade da demonstracao.

O schema auxiliar esta em [`database/rotafacil.sql`](database/rotafacil.sql).
Nao e necessario importar esse arquivo manualmente.

### 6.4. Regra Importante Para Clientes

Admin e funcionario autenticam usando usuarios do SQLite. O cliente autentica
com CNPJ e senha do SQLite, mas o mesmo CNPJ tambem precisa existir na tabela
`cliente` do MySQL. Isso impede que a area do cliente carregue dados de outro
cadastro.

## 7. Executar o Projeto

### Opcao Recomendada No Windows

Com o MySQL ativo e o `.env` configurado, execute:

```powershell
.\iniciar_site_corrigido.bat
```

O script inicia o Flask na porta `8001`.

### Opcao Pelo Terminal

Tambem e possivel executar diretamente:

```powershell
python app.py
```

Depois abra:

```text
http://127.0.0.1:8001
```

Para encerrar o servidor, pressione `Ctrl+C` no terminal.

## 8. Acessos Iniciais Da Demonstracao

Na primeira inicializacao, o SQLite cria contas locais para teste:

| Perfil | Identificador | Senha inicial |
| --- | --- | --- |
| Administrador | `Administrador` | `admin123` |
| Funcionario | `João Silva` | `func123` |
| Cliente | `00000000000000` | `cliente123` |

O identificador interno e o **nome**, nao o e-mail. Para o login de cliente
funcionar, cadastre o CNPJ `00000000000000` tambem na tabela `cliente` do MySQL
ou utilize um CNPJ existente nos dois bancos.

Essas credenciais servem apenas para demonstracao local. Troque-as antes de
publicar o sistema.

## 9. Paginas Disponiveis

| Endereco | Finalidade |
| --- | --- |
| `/` | Pagina inicial institucional. |
| `/sobre` | Apresentacao do posto. |
| `/servicos` | Catalogo de servicos. |
| `/esg` | Pagina de sustentabilidade. |
| `/contato` | Formulario de contato. |
| `/login` | Login de cliente, funcionario e administrador. |
| `/admin/dashboard` | Painel administrativo protegido. |
| `/funcionario/dashboard` | Painel operacional protegido. |
| `/cliente/dashboard` | Area protegida do cliente. |

## 10. Logs, Backups E Relatorios

Durante o uso, o sistema cria arquivos locais:

```text
logs/sistema.log
logs/acesso.log
logs/auditoria.log
logs/erro.log
```

O backup automatico e verificado ao iniciar a aplicacao e depois
periodicamente. A pasta `backups/` pode receber:

```text
rotafacil_AAAAMMDD_HHMMSS.db
mysql_AAAAMMDD_HHMMSS.json
ultimo_backup.txt
```

Os dashboards tambem permitem exportar relatorios em CSV e PDF sem instalar
bibliotecas extras para gerar o PDF.

## 11. Estrutura Principal

```text
PostoNovaRota/
|-- app.py                       # Rotas, regras de negocio e inicializacao Flask
|-- iniciar_site_corrigido.bat   # Inicializacao simples no Windows
|-- run_8001.py                  # Inicializacao fixa na porta 8001
|-- requirements.txt             # Dependencias Python
|-- database/
|   |-- conexao.py               # Conexao com o SQLite auxiliar
|   |-- mysql_conexao.py         # Conexao com o MySQL principal
|   |-- rotafacil.sql            # Schema SQLite criado automaticamente
|   `-- acessos_mysql.sql        # Papeis e permissoes MySQL
|-- templates/                   # Paginas HTML com Jinja
|-- static/css/                  # Estilos e responsividade
|-- static/img/                  # Imagens do site
|-- utils/logger.py              # Logs separados por categoria
|-- logs/                        # Logs locais gerados durante o uso
`-- backups/                     # Backups locais automaticos
```

## 12. Solucao De Problemas

### Erro `SECRET_KEY nao configurada no .env`

Crie o arquivo `.env` na raiz e preencha `SECRET_KEY`.

### Erro de conexao com MySQL

Confira se o servico MySQL esta ativo, se a porta e `3306` e se usuario, senha
e banco no `.env` estao corretos.

### Erro `Schema MySQL incompativel`

O banco conectado nao corresponde ao DER esperado. Importe o schema operacional
correto e preserve os nomes exatos das tabelas e colunas.

### Porta ocupada

Use `.\iniciar_site_corrigido.bat`, que inicia o site em
`http://127.0.0.1:8001`.

### Muitos avisos nos templates HTML

Os arquivos usam Jinja, por exemplo `{{ variavel }}` e `{% for ... %}`. Essas
expressoes sao processadas pelo Flask e podem gerar falsos avisos em validadores
de HTML/CSS puro. O workspace desativa apenas a validacao de estilos HTML
embutidos para reduzir esses falsos positivos.

## 13. Cuidados Antes De Publicar

Antes de colocar o sistema em producao:

1. Troque todas as senhas de demonstracao.
2. Gere uma `SECRET_KEY` forte.
3. Nao envie `.env`, bancos locais, logs ou backups para o Git.
4. Use um usuario tecnico MySQL com permissoes limitadas.
5. Configure HTTPS e revise as variaveis `MAIL_*`.
