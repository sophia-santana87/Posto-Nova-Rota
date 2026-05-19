# Posto Nova Rota

Site e protótipo do sistema RotaFácil para o Posto Nova Rota.

## Como executar

1. Instale as dependências:

```powershell
pip install -r requirements.txt
```

2. Inicie o Flask:

```powershell
python app.py
```

3. Acesse no navegador:

```text
http://127.0.0.1:5000
```

## Telas disponíveis

- `/` - página institucional
- `/login` - seleção de perfil e login
- `/cliente` - área do cliente
- `/funcionario` - área do funcionário
- `/admin` - dashboard administrativo

## Formulário de contato

O formulário salva as mensagens no banco SQLite:

```text
database/rotafacil.db
```

Também mantém uma cópia de apoio em:

```text
logs/contatos.log
```

Assim não é necessário configurar senha de e-mail durante o desenvolvimento.

## Banco de dados

O projeto usa SQLite local por padrão, sem instalação extra.

- Conexão: `database/conexao.py`
- Schema: `database/rotafacil.sql`
- Arquivo gerado: `database/rotafacil.db`

O banco é inicializado automaticamente quando o Flask inicia.

## Acessos no MySQL

O banco `der_trabalho_bdii` pode usar papéis com `GRANT` e `REVOKE`.

Arquivo preparado:

```text
database/acessos_mysql.sql
```

Papéis sugeridos:

- `papel_admin_nova_rota`: acesso total.
- `papel_funcionario_nova_rota`: consulta dados, registra serviços/faturas e atualiza boletos.
- `papel_cliente_nova_rota`: leitura dos próprios dados, com filtro por CNPJ feito no Flask.
