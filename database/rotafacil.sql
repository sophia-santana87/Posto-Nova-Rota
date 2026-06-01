-- ============================================================
-- BANCO SQLITE AUXILIAR DO SITE
-- ============================================================
-- Este arquivo e como uma receita: quando o site inicia, o Python le
-- estes comandos e garante que as tabelas necessarias existem.
--
-- SQLite e um banco pequeno salvo em um unico arquivo:
-- database/rotafacil.db
--
-- Ele guarda somente dados auxiliares do site:
-- 1. mensagens enviadas pelo formulario de contato;
-- 2. usuarios e senhas usados para entrar no sistema.
--
-- Os dados principais da operacao nao ficam aqui. Clientes, veiculos,
-- servicos realizados, faturas e boletos ficam no banco MySQL rota_facil.
--

-- ============================================================
-- TABELA: contatos
-- ============================================================
-- Guarda as mensagens enviadas pela pagina publica de contato.
-- Pense nela como uma caixa de entrada: cada envio vira uma nova linha.
CREATE TABLE IF NOT EXISTS contatos (
    -- Identificador interno da mensagem.
    -- PRIMARY KEY: transforma esta coluna na identificacao principal da linha.
    -- AUTOINCREMENT: o SQLite escolhe automaticamente o proximo numero.
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Nome digitado pela pessoa no formulario.
    nome TEXT NOT NULL,

    -- E-mail informado para que a equipe possa responder.
    email TEXT NOT NULL,

    -- Telefone opcional. Como nao possui NOT NULL, pode ficar vazio.
    telefone TEXT,

    -- Tema escolhido ou digitado no formulario.
    assunto TEXT NOT NULL,

    -- Texto principal enviado pela pessoa.
    mensagem TEXT NOT NULL,

    -- Data e horario em que a mensagem foi salva.
    -- CURRENT_TIMESTAMP preenche automaticamente o momento atual.
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- TABELA: usuarios
-- ============================================================
-- Guarda as contas que podem entrar no site.
-- Cada usuario possui um perfil: cliente, funcionario ou administrador.
CREATE TABLE IF NOT EXISTS usuarios (
    -- Identificador interno da conta, criado automaticamente.
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Nome da pessoa ou da empresa dona da conta.
    nome TEXT NOT NULL,

    -- E-mail da conta.
    -- UNIQUE impede que duas contas usem o mesmo e-mail.
    -- Ele e opcional porque nao possui NOT NULL.
    email TEXT UNIQUE,

    -- Documento usado para identificar a conta.
    -- Para um cliente, normalmente recebe o CNPJ da empresa.
    -- UNIQUE impede que o mesmo documento seja cadastrado duas vezes.
    documento TEXT UNIQUE,

    -- Senha usada para entrar no sistema.
    -- O app.py converte senhas antigas para um formato protegido (hash).
    senha TEXT NOT NULL,

    -- Perfil da conta.
    -- CHECK permite somente os tres valores listados abaixo.
    -- Isso evita salvar um tipo desconhecido por engano.
    tipo TEXT NOT NULL CHECK (tipo IN ('cliente', 'funcionario', 'admin')),

    -- Controla se a conta pode entrar no sistema.
    -- No SQLite, 1 representa ativo e 0 representa desativado.
    -- DEFAULT 1 faz uma conta nova comecar ativa automaticamente.
    ativo INTEGER NOT NULL DEFAULT 1,

    -- Data e horario em que a conta foi cadastrada.
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- USUARIOS INICIAIS PARA DESENVOLVIMENTO
-- ============================================================
-- Estes registros facilitam os testes locais logo apos criar o banco.
--
-- INSERT adiciona linhas na tabela usuarios.
-- OR IGNORE evita um erro caso um registro igual ja exista.
-- Por exemplo: ao reiniciar o site, o SQLite nao tenta duplicar o admin.
--
-- Cada documento precisa ser diferente porque a coluna documento e UNIQUE.
-- Estas senhas sao apenas iniciais para o ambiente local de desenvolvimento.
INSERT OR IGNORE INTO usuarios (id, nome, email, documento, senha, tipo) VALUES
    -- Conta com acesso administrativo.
    (1, 'Administrador', 'admin@novarota.local', '99999999999999', 'admin123', 'admin'),

    -- Conta usada para testar o painel de funcionario.
    (2, 'Joao Silva', 'funcionario@novarota.local', '11111111111111', 'func123', 'funcionario'),

    -- Conta usada para testar o painel de cliente.
    -- O documento deve corresponder a um CNPJ cadastrado no MySQL.
    (3, 'Empresa Exemplo Ltda', 'cliente@novarota.local', '00000000000000', 'cliente123', 'cliente');
