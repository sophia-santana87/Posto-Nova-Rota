from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'rotafacil.db'
SCHEMA_PATH = BASE_DIR / 'rotafacil.sql'


def get_connection():
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    return conexao


def init_db():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f'Arquivo de schema não encontrado: {SCHEMA_PATH}')

    with get_connection() as conexao:
        conexao.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
        conexao.commit()


def salvar_mensagem_contato(dados):
    with get_connection() as conexao:
        conexao.execute(
            """
            INSERT INTO contatos (
                nome,
                email,
                telefone,
                assunto,
                mensagem
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                dados.get('nome'),
                dados.get('email'),
                dados.get('telefone') or None,
                dados.get('assunto'),
                dados.get('mensagem'),
            ),
        )
        conexao.commit()
