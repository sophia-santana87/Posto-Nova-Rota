import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logger(name, log_file):
    """Configurar logger com arquivo rotativo"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Criar pasta de logs se não existir
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True)
    
    # Handler para arquivo com rotação (10 MB, máx 5 arquivos)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    # Handler para console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Formato detalhado
    formatter = logging.Formatter(
        '[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        datefmt='%d/%m/%Y %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Inicializar loggers específicos
logger_sistema = setup_logger('sistema', 'logs/sistema.log')
logger_acesso = setup_logger('acesso', 'logs/acesso.log')
logger_auditoria = setup_logger('auditoria', 'logs/auditoria.log')
logger_erro = setup_logger('erro', 'logs/erro.log')