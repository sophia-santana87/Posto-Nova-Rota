import mysql.connector
import os
from dotenv import load_dotenv

# ============================================================
# CONEXAO AUTOMATICA DO SITE COM O MYSQL
# ============================================================
# Este arquivo funciona como uma ponte entre o site Flask e o banco
# principal MySQL chamado rota_facil.
#
# Ele nao cria tabelas e nao guarda dados sozinho. Sua tarefa e:
# 1. ler as configuracoes de acesso;
# 2. abrir uma conexao com o MySQL;
# 3. enviar uma consulta SQL;
# 4. receber o resultado;
# 5. fechar a conexao.
#
# A conexao do SQLTools e diferente desta conexao:
# - SQLTools: permite que uma pessoa consulte o MySQL manualmente no VS Code.
# - Este arquivo: permite que o site consulte o MySQL automaticamente.
#
# Mesmo quando o SQLTools esta conectado, o site ainda precisa deste arquivo.

# Carrega as configuracoes privadas escritas no arquivo .env.
# O .env nao deve subir para o Git porque pode conter senhas.
load_dotenv()


def get_mysql_config():
    """Monta os dados necessarios para conectar ao banco principal rota_facil."""

    # Procura a senha definida no arquivo .env.
    senha = os.getenv('MYSQL_PASSWORD', '')

    # Compatibilidade temporaria com o ambiente local atual.
    # Em um sistema de producao, a senha deve existir somente no .env.
    # Uma senha real nao deve ficar escrita diretamente no codigo-fonte.
    if senha in ('', 'sua-senha'):
        senha = 'Fl@qu1nh@'

    # Cria um dicionario com as informacoes exigidas pelo MySQL.
    # Caso algum item nao esteja no .env, usa o valor padrao indicado.
    return {
        # Computador onde o servidor MySQL esta funcionando.
        'host': os.getenv('MYSQL_HOST', 'localhost'),

        # Porta padrao utilizada pelo MySQL.
        'port': int(os.getenv('MYSQL_PORT', '3306')),

        # Conta tecnica utilizada pelo site para falar com o MySQL.
        'user': os.getenv('MYSQL_USER', 'root'),

        # Senha da conta tecnica.
        'password': senha,

        # Nome do banco principal que sera consultado.
        'database': os.getenv('MYSQL_DATABASE', 'rota_facil'),
    }


def get_mysql_connection():
    """Abre uma nova conexao com o MySQL usando a configuracao acima."""

    # O operador ** entrega cada item do dicionario como configuracao.
    return mysql.connector.connect(**get_mysql_config())


def fetch_one(query, params=None):
    """Executa uma consulta SELECT e devolve somente o primeiro registro."""

    # Abre uma conexao nova apenas para esta operacao.
    conexao = get_mysql_connection()

    # dictionary=True permite acessar colunas pelo nome.
    # Exemplo: cliente['cnpj'] em vez de cliente[0].
    cursor = conexao.cursor(dictionary=True)
    try:
        # Envia a consulta e seus valores separadamente para o MySQL.
        cursor.execute(query, params or ())

        # Retorna apenas a primeira linha encontrada.
        return cursor.fetchone()
    finally:
        # Fecha os recursos mesmo se algum erro acontecer.
        cursor.close()
        conexao.close()


def fetch_all(query, params=None):
    """Executa uma consulta SELECT e devolve todos os registros encontrados."""

    # Esta funcao e parecida com fetch_one, mas devolve uma lista de linhas.
    conexao = get_mysql_connection()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()


def execute_query(query, params=None):
    """Executa INSERT, UPDATE ou DELETE quando nao precisamos do novo id."""

    # Use esta funcao quando quiser adicionar, alterar ou excluir dados.
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())

        # Confirma definitivamente a alteracao no MySQL.
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()


def execute_insert_id(query, params=None):
    """Executa um INSERT e devolve o id criado automaticamente pelo MySQL."""

    # Use esta funcao quando o codigo precisar saber o id do novo registro.
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())
        conexao.commit()

        # Exemplo: depois de criar uma fatura, devolve o numero dela.
        return cursor.lastrowid
    finally:
        cursor.close()
        conexao.close()
