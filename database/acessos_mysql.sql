-- Controle de acessos MySQL para o banco der_trabalho_bdii.
-- Execute este arquivo conectado como root ou outro usuário com permissão de GRANT.
--
-- Observação:
-- GRANT/REVOKE controla o que cada usuário técnico pode fazer no banco.
-- As permissões de tela do site devem ser reforçadas no Flask pelo perfil logado.

CREATE ROLE IF NOT EXISTS 'papel_admin_nova_rota';
CREATE ROLE IF NOT EXISTS 'papel_funcionario_nova_rota';
CREATE ROLE IF NOT EXISTS 'papel_cliente_nova_rota';

-- ADMINISTRADOR
-- Acesso total ao banco do sistema.
GRANT ALL PRIVILEGES ON der_trabalho_bdii.* TO 'papel_admin_nova_rota';

-- FUNCIONÁRIO
-- Pode consultar clientes, veículos, serviços, faturas e boletos.
-- Pode registrar serviços e atualizar status de boleto/pagamento.
-- Não pode excluir dados sensíveis nem alterar estrutura do banco.
GRANT SELECT ON der_trabalho_bdii.`cliente` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`endereço` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`veiculo` TO 'papel_funcionario_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`serviço_utilizado` TO 'papel_funcionario_nova_rota';
GRANT SELECT, INSERT, UPDATE ON der_trabalho_bdii.`serviço` TO 'papel_funcionario_nova_rota';
GRANT SELECT, INSERT ON der_trabalho_bdii.`fatura` TO 'papel_funcionario_nova_rota';
GRANT SELECT, UPDATE ON der_trabalho_bdii.`boleto` TO 'papel_funcionario_nova_rota';

-- CLIENTE
-- Acesso técnico somente de leitura.
-- Restrição por CNPJ deve ser feita no Flask, porque GRANT do MySQL não filtra linha por cliente.
GRANT SELECT ON der_trabalho_bdii.`cliente` TO 'papel_cliente_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`veiculo` TO 'papel_cliente_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`fatura` TO 'papel_cliente_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`boleto` TO 'papel_cliente_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`serviço` TO 'papel_cliente_nova_rota';
GRANT SELECT ON der_trabalho_bdii.`serviço_utilizado` TO 'papel_cliente_nova_rota';

-- Usuários técnicos sugeridos.
-- Troque as senhas antes de executar em ambiente real.
CREATE USER IF NOT EXISTS 'nova_rota_admin'@'localhost' IDENTIFIED BY 'trocar_senha_admin';
CREATE USER IF NOT EXISTS 'nova_rota_funcionario'@'localhost' IDENTIFIED BY 'trocar_senha_funcionario';
CREATE USER IF NOT EXISTS 'nova_rota_cliente'@'localhost' IDENTIFIED BY 'trocar_senha_cliente';

GRANT 'papel_admin_nova_rota' TO 'nova_rota_admin'@'localhost';
GRANT 'papel_funcionario_nova_rota' TO 'nova_rota_funcionario'@'localhost';
GRANT 'papel_cliente_nova_rota' TO 'nova_rota_cliente'@'localhost';

SET DEFAULT ROLE 'papel_admin_nova_rota' TO 'nova_rota_admin'@'localhost';
SET DEFAULT ROLE 'papel_funcionario_nova_rota' TO 'nova_rota_funcionario'@'localhost';
SET DEFAULT ROLE 'papel_cliente_nova_rota' TO 'nova_rota_cliente'@'localhost';

FLUSH PRIVILEGES;

-- Exemplos de revogação, se precisar limitar depois:
-- REVOKE UPDATE ON der_trabalho_bdii.`boleto` FROM 'papel_funcionario_nova_rota';
-- REVOKE INSERT ON der_trabalho_bdii.`fatura` FROM 'papel_funcionario_nova_rota';
