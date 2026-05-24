import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_mysql_config():
    senha = os.getenv('MYSQL_PASSWORD', '')
    if senha in ('', 'sua-senha'):
        senha = 'Fl@qu1nh@'
    return {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', '3306')),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': senha,
        'database': os.getenv('MYSQL_DATABASE', 'der_trabalho_bdii'),
    }

def get_mysql_connection():
    return mysql.connector.connect(**get_mysql_config())

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

def execute_query(query, params=None):
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()

def execute_insert_id(query, params=None):
    conexao = get_mysql_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute(query, params or ())
        conexao.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        conexao.close()
