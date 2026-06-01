import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Imagine que o site possui alguns cadernos para anotar o que acontece.
# Se algo der errado ou alguem entrar no sistema, podemos olhar esses
# cadernos depois para entender o que ocorreu.
#
# Esta funcao prepara um desses cadernos.
# name: nome do assunto que sera anotado, como "erro" ou "acesso".
# log_file: caminho do arquivo onde as anotacoes serao guardadas.
def setup_logger(name, log_file):
    """Prepara um caderno de registros e tambem mostra mensagens no terminal."""

    # Cria o objeto que recebera as mensagens deste assunto.
    logger = logging.getLogger(name)

    # DEBUG permite que o terminal mostre ate mensagens bem detalhadas.
    logger.setLevel(logging.DEBUG)

    # Descobre a pasta do arquivo e a cria caso ela ainda nao exista.
    # Por exemplo: para "logs/erro.log", cria a pasta "logs".
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)

    # Prepara o arquivo que vai guardar as mensagens.
    # Quando o arquivo chegar a 10 MB, ele sera arquivado e um novo sera criado.
    # Isso evita que um unico arquivo cresca para sempre.
    # O sistema guarda no maximo cinco arquivos antigos.
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )

    # No arquivo, salva apenas mensagens importantes: INFO, WARNING e ERROR.
    file_handler.setLevel(logging.INFO)

    # Tambem prepara a exibicao das mensagens no terminal.
    # O terminal mostra inclusive as mensagens detalhadas de DEBUG.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Define como cada anotacao aparecera.
    # Exemplo: [01/06/2026 10:30:00] erro - ERROR - Falha ao conectar
    formatter = logging.Formatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        datefmt='%d/%m/%Y %H:%M:%S'
    )

    # Usa o mesmo formato no arquivo e no terminal.
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Entrega as duas formas de registro ao logger:
    # uma escreve no arquivo e a outra mostra no terminal.
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Devolve o caderno pronto para que outros arquivos possam usa-lo.
    return logger


# Cria quatro cadernos separados por assunto.
# Assim fica mais facil encontrar uma informacao depois.
logger_sistema = setup_logger('sistema', 'logs/sistema.log')
logger_acesso = setup_logger('acesso', 'logs/acesso.log')
logger_auditoria = setup_logger('auditoria', 'logs/auditoria.log')
logger_erro = setup_logger('erro', 'logs/erro.log')
