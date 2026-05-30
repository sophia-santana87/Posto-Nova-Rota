-- Controle de acessos MySQL para o banco rota_facil.

CREATE ROLE IF NOT EXISTS 'papel_admin_nova_rota';
CREATE ROLE IF NOT EXISTS 'papel_funcionario_nova_rota';
CREATE ROLE IF NOT EXISTS 'papel_cliente_nova_rota';

-- ADMINISTRADOR
-- Acesso total ao banco do sistema.
GRANT ALL PRIVILEGES ON rota_facil.* TO 'papel_admin_nova_rota';

-- FUNCIONÁRIO
-- Pode consultar clientes, veículos, serviços, faturas e boletos.
-- Pode registrar serviços e atualizar status de boleto/pagamento.
-- Não pode excluir dados sensíveis nem alterar estrutura do banco.
GRANT SELECT ON rota_facil.`cliente` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON rota_facil.`endereço` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON rota_facil.`veiculo` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON rota_facil.`serviço_utilizado` TO 'papel_funcionario_nova_rota';
GRANT SELECT, INSERT, UPDATE ON rota_facil.`serviço` TO 'papel_funcionario_nova_rota';
GRANT SELECT, INSERT ON rota_facil.`fatura` TO 'papel_funcionario_nova_rota';
GRANT SELECT, UPDATE ON rota_facil.`boleto` TO 'papel_funcionario_nova_rota';

-- CLIENTE
-- Acesso técnico somente de leitura.
-- Restrição por CNPJ deve ser feita no Flask, porque GRANT do MySQL não filtra linha por cliente.
GRANT SELECT ON rota_facil.`cliente` TO 'papel_cliente_nova_rota';
GRANT SELECT ON rota_facil.`veiculo` TO 'papel_cliente_nova_rota';
GRANT SELECT ON rota_facil.`fatura` TO 'papel_cliente_nova_rota';
GRANT SELECT ON rota_facil.`boleto` TO 'papel_cliente_nova_rota';
GRANT SELECT ON rota_facil.`serviço` TO 'papel_cliente_nova_rota';
GRANT SELECT ON rota_facil.`serviço_utilizado` TO 'papel_cliente_nova_rota';

-- ADMINISTRADOR
-- A aplicação usa o usuário técnico nova_rota_app, criado diretamente no MySQL.
GRANT 'papel_admin_nova_rota' TO 'nova_rota_app'@'localhost';
SET DEFAULT ROLE 'papel_admin_nova_rota' TO 'nova_rota_app'@'localhost';

FLUSH PRIVILEGES;

-- Exemplos de revogação, se precisar limitar depois:
-- REVOKE UPDATE ON rota_facil.`boleto` FROM 'papel_funcionario_nova_rota';
-- REVOKE INSERT ON rota_facil.`fatura` FROM 'papel_funcionario_nova_rota';
