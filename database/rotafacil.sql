CREATE TABLE IF NOT EXISTS contatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    telefone TEXT,
    assunto TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE,
    documento TEXT UNIQUE,
    senha TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('cliente', 'funcionario', 'admin')),
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    cnpj TEXT UNIQUE NOT NULL,
    razao_social TEXT NOT NULL,
    telefone TEXT,
    email TEXT,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT,
    valor_base REAL NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS boletos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    vencimento DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'em_aberto' CHECK (status IN ('em_aberto', 'pago', 'atrasado')),
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

INSERT OR IGNORE INTO usuarios (id, nome, email, documento, senha, tipo) VALUES
    (1, 'Administrador', 'admin@novarota.local', '00000000000000', 'admin123', 'admin'),
    (2, 'João Silva', 'funcionario@novarota.local', '11111111111111', 'func123', 'funcionario'),
    (3, 'Empresa Exemplo Ltda', 'cliente@novarota.local', '00000000000000', 'cliente123', 'cliente');

INSERT OR IGNORE INTO clientes (id, usuario_id, cnpj, razao_social, telefone, email) VALUES
    (1, 3, '00.000.000/0000-00', 'Empresa Exemplo Ltda', '(00) 00000-0000', 'cliente@novarota.local');

INSERT OR IGNORE INTO servicos (id, nome, descricao, valor_base) VALUES
    (1, 'Combustível', 'Abastecimento com qualidade e segurança.', 0),
    (2, 'Lavagem', 'Lavagem simples e completa para seu veículo.', 80),
    (3, 'Estacionamento Rotativo', 'Mais praticidade e controle para o seu dia.', 15),
    (4, 'Estacionamento Mensal', 'Soluções completas para empresas e frotas.', 250);

INSERT OR IGNORE INTO boletos (id, cliente_id, descricao, valor, vencimento, status) VALUES
    (1, 1, 'Serviços - Outubro/2026', 1250.00, '2026-11-20', 'em_aberto'),
    (2, 1, 'Serviços - Setembro/2026', 960.00, '2026-10-20', 'pago'),
    (3, 1, 'Serviços - Agosto/2026', 1100.00, '2026-09-20', 'pago');
