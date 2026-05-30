import mysql.connector
import os
from dotenv import load_dotenv

# Carrega as configuracoes privadas escritas no arquivo .env.
load_dotenv()


def get_mysql_config():
    """Monta os dados necessarios para conectar ao banco principal rota_facil."""
    senha = os.getenv('MYSQL_PASSWORD', '')
    if senha in ('', 'sua-senha'):
        senha = 'Fl@qu1nh@'
    return {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': senha,
        'database': os.getenv('MYSQL_DATABASE', 'rota_facil'),
    }


def get_mysql_connection():
    """Abre uma nova conexao com o MySQL usando a configuracao acima."""
    return mysql.connector.connect(**get_mysql_config())


def fetch_one(query, params=None):
    """Executa uma consulta SELECT e devolve somente o primeiro registro."""
    conexao = get_mysql_connection()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        return cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()


def fetch_all(query, params=None):
    """Executa uma consulta SELECT e devolve todos os registros encontrados."""
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
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()


def execute_insert_id(query, params=None):
    """Executa um INSERT e devolve o id criado automaticamente pelo MySQL."""
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())
        conexao.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conexao.close()
