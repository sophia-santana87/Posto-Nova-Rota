from pathlib import Path
import json
import os

import mysql.connector


ROOT_DIR = Path(__file__).resolve().parent.parent
SQLTOOLS_PATH = ROOT_DIR / '.vscode' / 'settings.json'


def _config_sqltools():
    if not SQLTOOLS_PATH.exists():
        return {}

    with SQLTOOLS_PATH.open(encoding='utf-8') as arquivo:
        settings = json.load(arquivo)

    for conexao in settings.get('sqltools.connections', []):
        if conexao.get('name') == 'Local instance MySQL80':
            return conexao

    return {}


def get_mysql_config():
    sqltools = _config_sqltools()
    return {
        'host': os.getenv('MYSQL_HOST', sqltools.get('server', 'localhost')),
        'port': int(os.getenv('MYSQL_PORT', sqltools.get('port', 3306))),
        'user': os.getenv('MYSQL_USER', sqltools.get('username', 'root')),
        'password': os.getenv('MYSQL_PASSWORD', sqltools.get('password', '')),
        'database': os.getenv('MYSQL_DATABASE', sqltools.get('database', 'der_trabalho_bdii')),
    }


def get_mysql_connection(dictionary=False):
    return mysql.connector.connect(**get_mysql_config(), autocommit=False)


def fetch_one(query, params=None):
    conexao = get_mysql_connection()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        return cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()


def fetch_all(query, params=None):
    conexao = get_mysql_connection()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        return cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()
