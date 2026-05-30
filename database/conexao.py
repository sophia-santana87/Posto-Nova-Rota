from pathlib import Path
import sqlite3

# Este arquivo cuida do banco SQLite auxiliar.
# Ele nao substitui o MySQL rota_facil: serve para dados locais do site,
# como usuarios que fazem login e mensagens enviadas pelo formulario.
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'rotafacil.db'
SCHEMA_PATH = BASE_DIR / 'rotafacil.sql'


def get_connection():
    """Abre o arquivo SQLite e permite acessar cada coluna pelo nome."""
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    return conexao


def init_db():
    """Cria as tabelas auxiliares ao iniciar o site, caso ainda nao existam."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f'Arquivo de schema não encontrado: {SCHEMA_PATH}')

    # executescript executa de uma vez todas as instrucoes de rotafacil.sql.
    with get_connection() as conexao:
        conexao.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
        conexao.commit()


def salvar_mensagem_contato(dados):
    """Guarda no SQLite uma mensagem recebida pela pagina de contato."""
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
