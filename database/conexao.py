from pathlib import Path
import sqlite3

# ============================================================
# CONEXAO COM O SQLITE AUXILIAR
# ============================================================
# Este arquivo cuida do pequeno banco SQLite usado pelo site.
#
# O SQLite nao precisa de um servidor separado. Ele salva os dados
# diretamente em um arquivo chamado rotafacil.db dentro desta pasta.
#
# Ele nao substitui o MySQL rota_facil. Cada banco possui uma tarefa:
# - SQLite: guarda usuarios de login e mensagens do formulario de contato.
# - MySQL: guarda clientes, veiculos, servicos, faturas e boletos.
#
# A conexao do SQLTools tambem nao interfere neste arquivo. O SQLTools
# serve para uma pessoa consultar bancos manualmente pelo VS Code.
# Este codigo serve para o site consultar o SQLite automaticamente.

# Descobre o caminho da pasta "database", independentemente de onde
# o comando para iniciar o site foi executado.
BASE_DIR = Path(__file__).resolve().parent

# Caminho do banco SQLite preenchido de verdade.
# Este arquivo e criado automaticamente caso ainda nao exista.
DB_PATH = BASE_DIR / 'rotafacil.db'

# Caminho da receita SQL usada para criar as tabelas auxiliares.
SCHEMA_PATH = BASE_DIR / 'rotafacil.sql'


def get_connection():
    """Abre o arquivo SQLite e permite acessar cada coluna pelo nome."""

    # Abre uma conexao com o arquivo rotafacil.db.
    conexao = sqlite3.connect(DB_PATH)

    # Permite acessar uma coluna usando seu nome.
    # Exemplo: usuario['nome'] em vez de usuario[1].
    conexao.row_factory = sqlite3.Row
    return conexao


def init_db():
    """Cria as tabelas auxiliares ao iniciar o site, caso ainda nao existam."""

    # Se a receita SQL sumir, interrompe a inicializacao e explica o problema.
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f'Arquivo de schema nao encontrado: {SCHEMA_PATH}')

    # Le o rotafacil.sql e executa seus comandos de uma vez.
    # As tabelas sao criadas somente se ainda nao existirem.
    with get_connection() as conexao:
        conexao.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))

        # Confirma as alteracoes no arquivo rotafacil.db.
        conexao.commit()


def salvar_mensagem_contato(dados):
    """Guarda no SQLite uma mensagem recebida pela pagina de contato."""

    # Abre uma conexao temporaria. Ao sair deste bloco, ela e fechada.
    with get_connection() as conexao:
        # Os sinais de interrogacao recebem os valores separadamente.
        # Isso e mais seguro do que montar um comando SQL juntando textos.
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

        # Grava definitivamente a nova mensagem no rotafacil.db.
        conexao.commit()
