import mimetypes
mimetypes.add_type('text/css', '.css')

import csv
import io
import json
import shutil
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
import os
import re
import smtplib

from dotenv import load_dotenv
from flask import Flask, Response, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from database.conexao import get_connection, init_db, salvar_mensagem_contato
from database.mysql_conexao import execute_insert_id, execute_query, fetch_all, fetch_one
from utils.logger import logger_acesso, logger_auditoria, logger_erro


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

app = Flask(
    __name__,
    static_folder=str(BASE_DIR / 'static'),
    static_url_path='/static',
    template_folder=str(BASE_DIR / 'templates'),
)

app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError('SECRET_KEY nao configurada no .env!')

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

csrf = CSRFProtect(app)

init_db()


SERVICOS_DETALHADOS = {
    'combustivel': [
        {
            'nome': 'Gasolina comum',
            'preco': Decimal('5.49'),
            'unidade': 'litro',
            'descricao': 'Combustivel de boa estabilidade para uso diario, com controle de qualidade e rendimento equilibrado.',
        },
        {
            'nome': 'Gasolina aditivada',
            'preco': Decimal('5.79'),
            'unidade': 'litro',
            'descricao': 'Contem aditivos detergentes e dispersantes que ajudam a manter bicos, valvulas e camara de combustao mais limpos.',
        },
        {
            'nome': 'Etanol',
            'preco': Decimal('3.89'),
            'unidade': 'litro',
            'descricao': 'Etanol hidratado de alta qualidade, com queima mais limpa, boa resposta do motor e origem renovavel.',
        },
        {
            'nome': 'Diesel S10',
            'preco': Decimal('6.09'),
            'unidade': 'litro',
            'descricao': 'Diesel com baixo teor de enxofre, indicado para motores modernos e para uma operacao mais eficiente da frota.',
        },
    ],
    'lavagem': [
        {
            'nome': 'Lavagem simples',
            'preco': Decimal('25.00'),
            'unidade': 'servico',
            'descricao': 'Limpeza externa rapida para remover poeira, marcas do uso diario e renovar a apresentacao do veiculo.',
        },
        {
            'nome': 'Lavagem completa',
            'preco': Decimal('35.00'),
            'unidade': 'servico',
            'descricao': 'Cuidado externo e interno, com atencao a rodas, vidros, painel e acabamento geral.',
        },
        {
            'nome': 'Higienizacao interna',
            'preco': Decimal('60.00'),
            'unidade': 'servico',
            'descricao': 'Processo focado em bancos, tapetes e superficies internas para mais conforto e sensacao de limpeza.',
        },
        {
            'nome': 'Acabamento especial',
            'preco': Decimal('45.00'),
            'unidade': 'servico',
            'descricao': 'Finalizacao com brilho e protecao visual para valorizar a pintura e melhorar a aparencia do carro.',
        },
    ],
    'estacionamento': [
        {
            'nome': 'Estacionamento rotativo',
            'preco': Decimal('8.00'),
            'unidade': 'hora',
            'descricao': 'Ideal para paradas curtas, com controle de entrada e saida para mais praticidade.',
        },
        {
            'nome': 'Diaria',
            'preco': Decimal('35.00'),
            'unidade': 'dia',
            'descricao': 'Opcao para quem precisa deixar o veiculo por mais tempo com previsibilidade de custo.',
        },
        {
            'nome': 'Estacionamento mensal',
            'preco': Decimal('150.00'),
            'unidade': 'mes',
            'descricao': 'Plano recorrente para empresas e clientes frequentes, facilitando controle e faturamento.',
        },
    ],
}


def brl(valor):
    try:
        numero = Decimal(str(valor or 0))
    except Exception:
        numero = Decimal('0')
    texto = f'{numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {texto}'


app.jinja_env.filters['brl'] = brl


@app.context_processor
def inject_globals():
    return {'current_year': datetime.now().year}


@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def somente_digitos(valor):
    return re.sub(r'\D', '', str(valor or ''))


def normalizar_placa(valor):
    return ''.join(caractere for caractere in (valor or '').upper() if caractere.isalnum())[:7]


def parse_veiculos_formulario(texto, modelo_padrao='', ano_padrao=''):
    veiculos = []
    vistos = set()
    modelo_padrao = (modelo_padrao or 'Não informado').strip() or 'Não informado'
    ano_padrao = int(ano_padrao or date.today().year)
    partes = re.split(r'[\n,;]+', texto or '')
    for parte in partes:
        if not parte.strip():
            continue
        campos = [campo.strip() for campo in re.split(r'\s*[-|]\s*', parte.strip()) if campo.strip()]
        placa = normalizar_placa(campos[0])
        if not placa or placa in vistos:
            continue
        modelo = campos[1] if len(campos) > 1 else modelo_padrao
        try:
            ano = int(somente_digitos(campos[2] if len(campos) > 2 else ano_padrao) or ano_padrao)
        except ValueError:
            ano = ano_padrao
        veiculos.append({'placa': placa, 'modelo': modelo[:28], 'ano': ano})
        vistos.add(placa)
    return veiculos


def mascarar_cnpj(cnpj):
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        return 'CNPJ protegido'
    return f'**.***.***/{digitos[8:12]}-{digitos[12:]}'


def mascarar_email(email):
    if not email or '@' not in email:
        return 'e-mail nao cadastrado'
    local, dominio = email.split('@', 1)
    if len(local) <= 4:
        local_mascarado = f'{local[:1]}***{local[-1:]}'
    else:
        local_mascarado = f'{local[:2]}***{local[-2:]}'
    return f'{local_mascarado}@{dominio}'


def senha_armazenada_e_hash(valor):
    return str(valor or '').startswith(('pbkdf2:', 'scrypt:'))


def senha_confere(usuario, senha):
    senha_armazenada = usuario['senha'] if usuario else ''
    if senha_armazenada_e_hash(senha_armazenada):
        return check_password_hash(senha_armazenada, senha)
    return senha_armazenada == senha


def senha_forte(senha):
    return bool(
        senha
        and len(senha) >= 8
        and re.search(r'[A-Z]', senha)
        and re.search(r'[a-z]', senha)
        and re.search(r'\d', senha)
        and re.search(r'[^A-Za-z0-9]', senha)
    )


SENHAS_PADRAO_FORTES = {
    ('admin', 'Administrador'): 'Admin@123',
    ('funcionario', 'João Silva'): 'Func@1234',
    ('funcionario', 'Joao Silva'): 'Func@1234',
    ('cliente', 'Alemanha Transportes SA'): 'Cliente@123',
    ('cliente', 'Empresa Exemplo Ltda'): 'Cliente@123',
}


def migrar_senhas_para_hash():
    with get_connection() as conexao:
        usuarios = conexao.execute('SELECT id, nome, tipo, senha FROM usuarios').fetchall()
        for usuario in usuarios:
            senha_atual = usuario['senha']
            if senha_armazenada_e_hash(senha_atual):
                continue
            nova_senha = SENHAS_PADRAO_FORTES.get((usuario['tipo'], usuario['nome']))
            if not nova_senha:
                nova_senha = f'{usuario["tipo"].title()}@123'
            if not senha_forte(nova_senha):
                raise ValueError('Senha padrao gerada nao atende a politica minima.')
            conexao.execute(
                'UPDATE usuarios SET senha = ? WHERE id = ?',
                (generate_password_hash(nova_senha), usuario['id']),
            )
        conexao.commit()


def data_hora_br(valor):
    if not valor:
        return '-'
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    texto = str(valor)
    for formato in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            data = datetime.strptime(texto[:19], formato)
            return data.strftime('%d/%m/%Y %H:%M') if 'H' in formato else data.strftime('%d/%m/%Y')
        except ValueError:
            continue
    return texto


app.jinja_env.filters['data_hora_br'] = data_hora_br


def normalizar_linha_relatorio(linha):
    return {
        chave: data_hora_br(valor) if isinstance(valor, (date, datetime)) else str(valor or '')
        for chave, valor in dict(linha).items()
    }


def resposta_csv(nome_arquivo, secoes):
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=';')
    escritor.writerow(['Posto Nova Rota'])
    escritor.writerow(['Relatorio gerado em', datetime.now().strftime('%d/%m/%Y %H:%M')])
    escritor.writerow([])
    for indice, (titulo, linhas) in enumerate(secoes, start=1):
        escritor.writerow([f'{indice}. {titulo}'])
        escritor.writerow(['Total de registros', len(linhas)])
        if linhas:
            colunas = list(linhas[0].keys())
            escritor.writerow(colunas)
            for linha in linhas:
                escritor.writerow([linha.get(coluna, '') for coluna in colunas])
        else:
            escritor.writerow(['Sem registros'])
        escritor.writerow([])
    conteudo = '\ufeff' + saida.getvalue()
    return Response(
        conteudo,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={nome_arquivo}.csv'},
    )


def escapar_pdf(texto):
    return str(texto).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def resposta_pdf(nome_arquivo, secoes):
    def texto_pdf(comandos, x, y, texto, tamanho=10, fonte='F1', cor=(0.06, 0.13, 0.24)):
        r, g, b = cor
        comandos.append(f'{r:.3f} {g:.3f} {b:.3f} rg')
        comandos.append('BT')
        comandos.append(f'/{fonte} {tamanho} Tf')
        comandos.append(f'{x} {y} Td')
        comandos.append(f'({escapar_pdf(texto)}) Tj')
        comandos.append('ET')

    def retangulo_pdf(comandos, x, y, largura, altura, cor):
        r, g, b = cor
        comandos.append(f'{r:.3f} {g:.3f} {b:.3f} rg')
        comandos.append(f'{x} {y} {largura} {altura} re f')

    def quebrar_texto(texto, limite=92):
        palavras = str(texto or '').split()
        linhas = []
        atual = ''
        for palavra in palavras:
            candidato = f'{atual} {palavra}'.strip()
            if len(candidato) > limite and atual:
                linhas.append(atual)
                atual = palavra
            else:
                atual = candidato
        if atual:
            linhas.append(atual)
        return linhas or ['']

    paginas = []
    comandos = []
    y = 0
    numero_pagina = 0

    def nova_pagina(subtitulo='Relatorio executivo'):
        nonlocal comandos, y, numero_pagina
        if comandos:
            paginas.append(comandos)
        numero_pagina += 1
        comandos = []
        retangulo_pdf(comandos, 0, 782, 595, 60, (0.05, 0.12, 0.22))
        retangulo_pdf(comandos, 0, 774, 595, 8, (0.04, 0.45, 0.78))
        texto_pdf(comandos, 40, 808, 'Posto Nova Rota', 20, 'F2', (1, 1, 1))
        texto_pdf(comandos, 40, 790, subtitulo, 10, 'F1', (0.88, 0.94, 1))
        texto_pdf(comandos, 420, 790, f'Pagina {numero_pagina}', 9, 'F1', (0.88, 0.94, 1))
        y = 738

    def garantir_espaco(altura):
        nonlocal y
        if y - altura < 52:
            nova_pagina('Continuação do relatório')

    nova_pagina('Relatorio executivo')
    texto_pdf(comandos, 40, y, f'Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 11, 'F1')
    y -= 28

    for indice, (titulo, registros) in enumerate(secoes, start=1):
        garantir_espaco(92)
        retangulo_pdf(comandos, 36, y - 36, 523, 42, (0.91, 0.96, 1))
        retangulo_pdf(comandos, 36, y - 36, 7, 42, (0.04, 0.45, 0.78))
        texto_pdf(comandos, 52, y - 10, f'{indice}. {titulo}', 14, 'F2')
        texto_pdf(comandos, 52, y - 27, f'{len(registros)} registro(s)', 9, 'F1', (0.28, 0.36, 0.47))
        y -= 58

        if not registros:
            garantir_espaco(30)
            texto_pdf(comandos, 52, y, 'Sem registros para esta seção.', 10, 'F1', (0.36, 0.42, 0.50))
            y -= 26
            continue

        for registro in registros[:12]:
            itens = list(registro.items())[:5]
            resumo = '  |  '.join(f'{chave}: {valor}' for chave, valor in itens)
            linhas = quebrar_texto(resumo, 88)
            altura = 22 + (len(linhas) * 12)
            garantir_espaco(altura + 8)
            retangulo_pdf(comandos, 48, y - altura + 8, 499, altura, (0.98, 0.99, 1))
            retangulo_pdf(comandos, 48, y - altura + 8, 4, altura, (0.14, 0.72, 0.55))
            linha_y = y - 8
            for linha in linhas:
                texto_pdf(comandos, 60, linha_y, linha, 8.5, 'F1')
                linha_y -= 12
            y -= altura + 8

        if len(registros) > 12:
            garantir_espaco(24)
            texto_pdf(
                comandos,
                52,
                y,
                f'Mais {len(registros) - 12} registro(s) disponíveis no CSV completo.',
                9,
                'F1',
                (0.04, 0.45, 0.78),
            )
            y -= 28

        y -= 8

    paginas.append(comandos)

    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>',
    ]

    kids = []
    for indice, pagina in enumerate(paginas):
        page_obj_id = 5 + (indice * 2)
        content_obj_id = page_obj_id + 1
        kids.append(f'{page_obj_id} 0 R')
        stream = '\n'.join(pagina).encode('latin-1', errors='replace')
        objetos.append(
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
            f'/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj_id} 0 R >>'
            .encode('ascii')
        )
        objetos.append(
            b'<< /Length ' + str(len(stream)).encode('ascii') + b' >>\nstream\n' + stream + b'\nendstream'
        )

    objetos[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(paginas)} >>'.encode('ascii')

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = []
    for indice, objeto in enumerate(objetos, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{indice} 0 obj\n'.encode('ascii'))
        pdf.extend(objeto)
        pdf.extend(b'\nendobj\n')
    inicio_xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n'.encode('ascii'))
    for offset in offsets:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        f'trailer << /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF'.encode('ascii')
    )
    return Response(
        bytes(pdf),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={nome_arquivo}.pdf'},
    )


def relatorio_servicos(where='', params=None, incluir_cnpj=True):
    colunas_cliente = 'c.razao_social AS cliente, c.cnpj, ' if incluir_cnpj else 'c.razao_social AS cliente, '
    linhas = fetch_all(
        'SELECT s.id_Serviço AS id, s.data_registro AS data, '
        f'{colunas_cliente}'
        's.Veiculo_placa_veiculo AS placa, su.nome AS servico, s.qunt_utilizada AS quantidade, '
        'su.valor_unitario, su.desconto '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN cliente_veiculo cv ON cv.placa_veiculo = s.Veiculo_placa_veiculo '
        'LEFT JOIN cliente c ON c.cnpj = cv.cliente_cnpj '
        f'{where} ORDER BY s.id_Serviço DESC LIMIT 500',
        params or (),
    )
    return [normalizar_linha_relatorio(linha) for linha in linhas]


def boletos_relatorio(where='', params=None, limite=500):
    return [normalizar_linha_relatorio(linha) for linha in listar_boletos(where, params or (), limite=limite)]


def eventos_auditoria(*termos):
    log_path = BASE_DIR / 'logs' / 'auditoria.log'
    if not log_path.exists():
        return []
    eventos = []
    termos_normalizados = [termo.lower() for termo in termos]
    for linha in log_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        texto = linha.lower()
        if all(termo in texto for termo in termos_normalizados):
            eventos.append({'evento': linha})
    return eventos[-80:]


def relatorio_admin():
    clientes = fetch_all(
        'SELECT cnpj, razao_social, telefone, email, Veiculo_placa_veiculo AS placa, Fatura_id_Fatura AS fatura '
        'FROM cliente ORDER BY razao_social LIMIT 500'
    )
    return [
        ('Clientes existentes', [normalizar_linha_relatorio(linha) for linha in clientes]),
        ('Clientes criados', eventos_auditoria('criou', 'cliente')),
        ('Clientes editados', eventos_auditoria('editou', 'cliente')),
        ('Boletos em aberto', boletos_relatorio("WHERE UPPER(b.status_pagamento) = 'EM ABERTO'")),
        (
            'Boletos em vencimento',
            boletos_relatorio(
                "WHERE UPPER(b.status_pagamento) = 'EM ABERTO' "
                'AND b.data_vencimento BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)'
            ),
        ),
        ('Boletos atrasados', boletos_relatorio("WHERE UPPER(b.status_pagamento) = 'ATRASADO'")),
        ('Boletos pagos', boletos_relatorio("WHERE UPPER(b.status_pagamento) = 'PAGO'")),
        ('Servicos prestados', relatorio_servicos()),
        ('Novos servicos cadastrados', eventos_auditoria('criou', 'servico')),
        ('Servicos atualizados', eventos_auditoria('editou', 'servico')),
        ('Novas vendas registradas', eventos_auditoria('registrou servico')),
    ]


def relatorio_funcionario():
    return [
        ('Boletos em aberto', boletos_relatorio("WHERE UPPER(b.status_pagamento) = 'EM ABERTO'")),
        (
            'Boletos em vencimento',
            boletos_relatorio(
                "WHERE UPPER(b.status_pagamento) = 'EM ABERTO' "
                'AND b.data_vencimento BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)'
            ),
        ),
        ('Boletos atrasados', boletos_relatorio("WHERE UPPER(b.status_pagamento) = 'ATRASADO'")),
        ('Servicos prestados', relatorio_servicos(incluir_cnpj=False)),
        ('Vendas registradas pela equipe', eventos_auditoria('registrou servico')),
    ]


def relatorio_cliente(cnpj):
    boletos = listar_boletos('WHERE c.cnpj = %s', (cnpj,), limite=500)
    servicos = relatorio_servicos(
        'WHERE c.cnpj = %s',
        (cnpj,),
        incluir_cnpj=False,
    )
    return [
        (
            'Meus boletos em aberto',
            [normalizar_linha_relatorio(linha) for linha in boletos if str(linha.get('status_pagamento') or '').upper() == 'EM ABERTO'],
        ),
        (
            'Meus boletos pagos',
            [normalizar_linha_relatorio(linha) for linha in boletos if str(linha.get('status_pagamento') or '').upper() == 'PAGO'],
        ),
        (
            'Meus boletos atrasados',
            [normalizar_linha_relatorio(linha) for linha in boletos if str(linha.get('status_pagamento') or '').upper() == 'ATRASADO'],
        ),
        ('Meus servicos utilizados', servicos),
    ]


def criar_backup_automatico():
    pasta = BASE_DIR / 'backups'
    pasta.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime('%Y%m%d_%H%M%S')
    sqlite_origem = BASE_DIR / 'database' / 'rotafacil.db'
    if sqlite_origem.exists():
        shutil.copy2(sqlite_origem, pasta / f'rotafacil_{carimbo}.db')

    backup_mysql = {}
    try:
        tabelas = fetch_all('SHOW TABLES')
        for tabela in tabelas:
            nome = next(iter(tabela.values()))
            if isinstance(nome, bytes):
                nome = nome.decode('utf-8')
            nome = str(nome)
            nome_sql = nome.replace('`', '``')
            backup_mysql[nome] = fetch_all(f'SELECT * FROM `{nome_sql}`')
        (pasta / f'mysql_{carimbo}.json').write_text(
            json.dumps(backup_mysql, ensure_ascii=False, default=str, indent=2),
            encoding='utf-8',
        )
    except Exception as exc:
        logger_erro.exception(f'Backup automatico MySQL falhou: {exc}')

    (pasta / 'ultimo_backup.txt').write_text(datetime.now().isoformat(), encoding='utf-8')
    logger_auditoria.info(f'Backup automatico criado em {pasta}')


def backup_esta_vencido():
    marcador = BASE_DIR / 'backups' / 'ultimo_backup.txt'
    if not marcador.exists():
        return True
    try:
        ultimo = datetime.fromisoformat(marcador.read_text(encoding='utf-8').strip())
        return datetime.now() - ultimo >= timedelta(hours=24)
    except Exception:
        return True


def rotina_backup_24h():
    while True:
        try:
            if backup_esta_vencido():
                criar_backup_automatico()
        except Exception as exc:
            logger_erro.exception(f'Erro na rotina de backup: {exc}')
        time.sleep(3600)


def iniciar_backup_automatico():
    if backup_esta_vencido():
        criar_backup_automatico()
    thread = threading.Thread(target=rotina_backup_24h, daemon=True)
    thread.start()


def garantir_modelo_cliente_veiculo():
    try:
        execute_query('ALTER TABLE cliente MODIFY Veiculo_placa_veiculo CHAR(7) NULL')
        execute_query('ALTER TABLE cliente MODIFY Fatura_id_Fatura INT NULL')
        execute_query(
            'CREATE TABLE IF NOT EXISTS cliente_veiculo ('
            'cliente_cnpj CHAR(14) NOT NULL, '
            'placa_veiculo CHAR(7) NOT NULL, '
            'PRIMARY KEY (cliente_cnpj, placa_veiculo), '
            'CONSTRAINT fk_cliente_veiculo_cliente FOREIGN KEY (cliente_cnpj) '
            'REFERENCES cliente(cnpj) ON DELETE CASCADE ON UPDATE CASCADE, '
            'CONSTRAINT fk_cliente_veiculo_veiculo FOREIGN KEY (placa_veiculo) '
            'REFERENCES veiculo(placa_veiculo) ON DELETE CASCADE ON UPDATE CASCADE)'
        )
        execute_query(
            'INSERT IGNORE INTO cliente_veiculo (cliente_cnpj, placa_veiculo) '
            'SELECT cnpj, Veiculo_placa_veiculo FROM cliente WHERE Veiculo_placa_veiculo IS NOT NULL'
        )
    except Exception as exc:
        logger_erro.exception(f'Nao foi possivel preparar vinculo cliente-veiculo: {exc}')


migrar_senhas_para_hash()
garantir_modelo_cliente_veiculo()
iniciar_backup_automatico()


def login_obrigatorio(*perfis):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get('tipo') not in perfis:
                return redirect(url_for('login', tipo=perfis[0] if perfis else 'cliente'))
            return func(*args, **kwargs)
        return wrapper
    return decorator


@app.route('/relatorios/<perfil>/<formato>')
@login_obrigatorio('admin', 'funcionario', 'cliente')
def exportar_relatorio(perfil, formato):
    usuario_tipo = session.get('tipo')
    perfil = perfil.lower()
    formato = formato.lower()

    if formato not in {'csv', 'pdf'}:
        return Response('Formato invalido.', status=400)
    if usuario_tipo != 'admin' and perfil != usuario_tipo:
        return Response('Acesso nao autorizado.', status=403)

    if perfil == 'admin':
        if usuario_tipo != 'admin':
            return Response('Acesso nao autorizado.', status=403)
        secoes = relatorio_admin()
    elif perfil == 'funcionario':
        secoes = relatorio_funcionario()
    elif perfil == 'cliente':
        cnpj = session.get('usuario_identificador')
        if usuario_tipo == 'admin':
            cnpj = request.args.get('cnpj') or cnpj
        if not cnpj:
            return Response('Cliente nao identificado.', status=400)
        secoes = relatorio_cliente(cnpj)
    else:
        return Response('Perfil invalido.', status=400)

    nome_arquivo = f'relatorio_{perfil}_{datetime.now().strftime("%Y%m%d_%H%M")}'
    logger_auditoria.info(f'Relatorio exportado perfil={perfil} formato={formato} usuario={usuario_tipo}')
    if formato == 'csv':
        return resposta_csv(nome_arquivo, secoes)
    return resposta_pdf(nome_arquivo, secoes)


def enviar_email(assunto, corpo, destinatario=None):
    host = os.getenv('MAIL_HOST')
    usuario = os.getenv('MAIL_USER')
    senha = os.getenv('MAIL_PASSWORD')
    remetente = os.getenv('MAIL_SENDER') or usuario
    destino = destinatario or os.getenv('MAIL_RECIPIENT') or usuario

    if not all([host, usuario, senha, remetente, destino]):
        return 'Configuracao de e-mail incompleta no .env.'

    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = destino
    msg.set_content(corpo)

    porta = int(os.getenv('MAIL_PORT', '587'))
    with smtplib.SMTP(host, porta, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(usuario, senha)
        smtp.send_message(msg)
    return ''


def carregar_precos_base():
    try:
        rows = fetch_all(
            'SELECT `id_Serviço_utilizado` AS id, nome, descrição AS descricao, '
            'valor_unitario, desconto FROM `serviço_utilizado` ORDER BY id'
        )
        return rows
    except Exception as exc:
        logger_erro.exception(f'Erro ao carregar servicos do MySQL: {exc}')
        return []


def resumo_boletos(where='', params=None):
    query = (
        'SELECT '
        'COUNT(*) AS total_boletos, '
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'PAGO' THEN 1 ELSE 0 END) AS boletos_pagos, "
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'EM ABERTO' THEN 1 ELSE 0 END) AS boletos_abertos, "
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'ATRASADO' THEN 1 ELSE 0 END) AS boletos_atrasados "
        'FROM boleto b '
        'JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura '
        'JOIN `serviço` s ON s.id_Serviço = f.Serviço_id_Serviço '
        'JOIN cliente_veiculo cv ON cv.placa_veiculo = s.Veiculo_placa_veiculo '
        'JOIN cliente c ON c.cnpj = cv.cliente_cnpj '
        f'{where}'
    )
    row = fetch_one(query, params or ())
    return {
        'total_boletos': int(row.get('total_boletos') or 0),
        'boletos_pagos': int(row.get('boletos_pagos') or 0),
        'boletos_abertos': int(row.get('boletos_abertos') or 0),
        'boletos_atrasados': int(row.get('boletos_atrasados') or 0),
    }


def listar_boletos(where='', params=None, limite=20):
    query = (
        'SELECT b.id_Boleto, b.data_vencimento, b.data_emissao, b.codigo_barras, b.status_pagamento, '
        'c.razao_social, c.cnpj, s.Veiculo_placa_veiculo AS placa_veiculo, '
        'su.nome AS servico, su.valor_unitario, su.desconto '
        'FROM boleto b '
        'JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura '
        'JOIN `serviço` s ON s.id_Serviço = f.Serviço_id_Serviço '
        'JOIN cliente_veiculo cv ON cv.placa_veiculo = s.Veiculo_placa_veiculo '
        'JOIN cliente c ON c.cnpj = cv.cliente_cnpj '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        f'{where} '
        'ORDER BY b.data_vencimento DESC '
        f'LIMIT {int(limite)}'
    )
    return fetch_all(query, params or ())


def faturamento_estimado():
    row = fetch_one(
        'SELECT SUM(s.qunt_utilizada * GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0)) AS total '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado'
    )
    return row.get('total') or Decimal('0')


def servicos_mais_utilizados():
    rows = fetch_all(
        'SELECT su.nome, COUNT(*) AS total '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'GROUP BY su.nome ORDER BY total DESC'
    )
    soma = sum(int(row['total'] or 0) for row in rows) or 1
    return [
        {
            'nome': row['nome'],
            'total': int(row['total'] or 0),
            'percentual': round((int(row['total'] or 0) / soma) * 100),
        }
        for row in rows
    ]


PERIODOS_CLIENTE = {
    '30': {'label': 'Últimos 30 dias', 'dias': 30},
    '90': {'label': 'Últimos 90 dias', 'dias': 90},
    '180': {'label': 'Últimos 6 meses', 'dias': 180},
    '365': {'label': 'Últimos 12 meses', 'dias': 365},
    'todos': {'label': 'Todo o histórico', 'dias': None},
}


def decimal_seguro(valor):
    try:
        return Decimal(str(valor or 0))
    except Exception:
        return Decimal('0')


def gerar_codigo_barras_demonstracao(fatura_id):
    base = f'23790{date.today().strftime("%Y%m%d")}{int(fatura_id):031d}'
    return somente_digitos(base)[:44].ljust(44, '0')


def listar_resumos_mensais(cliente_busca='', competencia='', limite=24):
    condicoes = []
    params = []
    if cliente_busca:
        condicoes.append('(c.razao_social LIKE %s OR c.cnpj LIKE %s)')
        params.extend([f'%{cliente_busca}%', f'%{cliente_busca}%'])
    if competencia:
        condicoes.append('DATE_FORMAT(s.data_registro, %s) = %s')
        params.extend(['%Y-%m', competencia])
    where = 'WHERE ' + ' AND '.join(condicoes) if condicoes else ''
    return fetch_all(
        'SELECT c.cnpj, c.razao_social, DATE_FORMAT(s.data_registro, %s) AS competencia, '
        'DATE_FORMAT(MIN(s.data_registro), %s) AS competencia_label, '
        'COUNT(DISTINCT s.id_Serviço) AS total_servicos, '
        'SUM(s.qunt_utilizada) AS total_quantidade, '
        'SUM(s.qunt_utilizada * GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0)) AS total_mes, '
        'SUM(CASE WHEN b.id_Boleto IS NULL THEN 1 ELSE 0 END) AS faturas_sem_boleto, '
        'SUM(CASE WHEN b.id_Boleto IS NOT NULL THEN 1 ELSE 0 END) AS faturas_com_boleto '
        'FROM cliente c '
        'JOIN cliente_veiculo cv ON cv.cliente_cnpj = c.cnpj '
        'JOIN `serviço` s ON s.Veiculo_placa_veiculo = cv.placa_veiculo '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'JOIN fatura f ON f.Serviço_id_Serviço = s.id_Serviço '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where} '
        'GROUP BY c.cnpj, c.razao_social, DATE_FORMAT(s.data_registro, %s) '
        'ORDER BY competencia DESC, c.razao_social '
        f'LIMIT {int(limite)}',
        ('%Y-%m', '%m/%Y', *params, '%Y-%m'),
    )


def listar_itens_resumo_mensal(cnpj, competencia):
    return fetch_all(
        'SELECT su.nome AS servico, COUNT(*) AS registros, SUM(s.qunt_utilizada) AS quantidade, '
        'SUM(s.qunt_utilizada * GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0)) AS subtotal '
        'FROM cliente_veiculo cv '
        'JOIN `serviço` s ON s.Veiculo_placa_veiculo = cv.placa_veiculo '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'WHERE cv.cliente_cnpj = %s AND DATE_FORMAT(s.data_registro, %s) = %s '
        'GROUP BY su.nome ORDER BY subtotal DESC',
        (cnpj, '%Y-%m', competencia),
    )


def gerar_boletos_resumo_mensal(cnpj, competencia, vencimento):
    faturas = fetch_all(
        'SELECT f.id_Fatura AS id '
        'FROM cliente_veiculo cv '
        'JOIN `serviço` s ON s.Veiculo_placa_veiculo = cv.placa_veiculo '
        'JOIN fatura f ON f.Serviço_id_Serviço = s.id_Serviço '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        'WHERE cv.cliente_cnpj = %s AND DATE_FORMAT(s.data_registro, %s) = %s AND b.id_Boleto IS NULL '
        'ORDER BY f.id_Fatura',
        (cnpj, '%Y-%m', competencia),
    )
    for fatura in faturas:
        execute_query(
            'INSERT INTO boleto (data_vencimento, data_emissao, codigo_barras, status_pagamento, Fatura_id_Fatura) '
            'VALUES (%s, %s, %s, %s, %s)',
            (vencimento, date.today().isoformat(), gerar_codigo_barras_demonstracao(fatura['id']), 'EM ABERTO', fatura['id']),
        )
    return len(faturas)


def calcular_resumo_cliente(servicos, boletos):
    total_gasto = Decimal('0')
    total_quantidade = Decimal('0')
    uso_por_servico = {}

    for servico in servicos:
        quantidade = decimal_seguro(servico.get('qunt_utilizada'))
        valor = decimal_seguro(servico.get('valor_unitario'))
        desconto = decimal_seguro(servico.get('desconto'))
        valor_final = max(valor - desconto, Decimal('0'))

        total_quantidade += quantidade
        total_gasto += quantidade * valor_final
        nome = servico.get('nome') or 'Servico'
        uso_por_servico[nome] = uso_por_servico.get(nome, Decimal('0')) + quantidade

    maior_uso = max(uso_por_servico.values(), default=Decimal('1')) or Decimal('1')
    total_usos_populares = sum(uso_por_servico.values(), Decimal('0')) or Decimal('1')
    servicos_populares = [
        {
            'nome': nome,
            'total': total,
            'percentual': int((total / maior_uso) * 100),
            'participacao': int((total / total_usos_populares) * 100),
        }
        for nome, total in sorted(uso_por_servico.items(), key=lambda item: item[1], reverse=True)[:4]
    ]

    boletos_abertos = [
        boleto for boleto in boletos
        if str(boleto.get('status_pagamento') or '').upper() == 'EM ABERTO'
    ]
    valor_em_aberto = sum(
        (
            max(
                decimal_seguro(boleto.get('valor_unitario')) - decimal_seguro(boleto.get('desconto')),
                Decimal('0'),
            )
            for boleto in boletos_abertos
        ),
        Decimal('0'),
    )

    ticket_medio = total_gasto / total_quantidade if total_quantidade else Decimal('0')
    return {
        'total_gasto': total_gasto,
        'total_quantidade': total_quantidade,
        'ticket_medio': ticket_medio,
        'servicos_populares': servicos_populares,
        'boletos_abertos': len(boletos_abertos),
        'valor_em_aberto': valor_em_aberto,
    }


def porcentagem_status(resumo):
    total = int(resumo.get('total_boletos') or 0) or 1
    pago = int(resumo.get('boletos_pagos') or 0)
    aberto = int(resumo.get('boletos_abertos') or 0)
    resumo['pct_pago'] = round((pago / total) * 100, 2)
    resumo['pct_aberto'] = round(((pago + aberto) / total) * 100, 2)
    return resumo


def boletos_por_status(status, limite=6):
    return listar_boletos(
        'WHERE UPPER(b.status_pagamento) = %s',
        (status.upper(),),
        limite=limite,
    )


def garantir_coluna_data_servico():
    try:
        coluna = fetch_one("SHOW COLUMNS FROM `serviço` LIKE 'data_registro'")
        if not coluna:
            logger_erro.error('Coluna data_registro nao encontrada na tabela servico.')
    except Exception as exc:
        logger_erro.exception(f'Nao foi possivel verificar data_registro em servico: {exc}')


def classe_status(status):
    status_normalizado = str(status or '').strip().upper()
    if status_normalizado == 'PAGO':
        return 'paid'
    if status_normalizado == 'ATRASADO':
        return 'late'
    return 'open'


app.jinja_env.globals['classe_status'] = classe_status


def fatura_mais_recente_por_placa(placa):
    placa = (placa or '').strip().upper()
    if not placa:
        return None
    row = fetch_one(
        'SELECT f.id_Fatura AS id '
        'FROM fatura f '
        'JOIN `serviço` s ON s.id_Serviço = f.Serviço_id_Serviço '
        'WHERE s.Veiculo_placa_veiculo = %s '
        'ORDER BY f.id_Fatura DESC LIMIT 1',
        (placa,),
    )
    return row.get('id') if row else None


def listar_faturas_operacionais(limite=200):
    return fetch_all(
        'SELECT f.id_Fatura AS id, c.razao_social, c.cnpj, s.Veiculo_placa_veiculo AS placa, '
        'su.nome AS servico, s.data_registro '
        'FROM fatura f '
        'JOIN `serviço` s ON s.id_Serviço = f.Serviço_id_Serviço '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN cliente_veiculo cv ON cv.placa_veiculo = s.Veiculo_placa_veiculo '
        'LEFT JOIN cliente c ON c.cnpj = cv.cliente_cnpj '
        'ORDER BY f.id_Fatura DESC LIMIT %s',
        (int(limite),),
    )


def salvar_veiculos_cliente(cnpj, veiculos):
    if not veiculos:
        raise ValueError('Informe pelo menos uma placa para o cliente.')
    for veiculo in veiculos:
        execute_query(
            'INSERT INTO veiculo (placa_veiculo, modelo, Ano_veiculo) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE modelo=VALUES(modelo), Ano_veiculo=VALUES(Ano_veiculo)',
            (veiculo['placa'], veiculo['modelo'], veiculo['ano']),
        )
    execute_query('DELETE FROM cliente_veiculo WHERE cliente_cnpj=%s', (cnpj,))
    for veiculo in veiculos:
        execute_query(
            'INSERT IGNORE INTO cliente_veiculo (cliente_cnpj, placa_veiculo) VALUES (%s, %s)',
            (cnpj, veiculo['placa']),
        )
    return veiculos[0]['placa']


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/sobre')
def sobre():
    return render_template('sobre.html')


@app.route('/servicos')
def servicos():
    return render_template('servicos.html', precos=carregar_precos_base())


@app.route('/servicos/combustivel')
def servico_combustivel():
    return render_template('servicos/combustivel.html', itens=SERVICOS_DETALHADOS['combustivel'])


@app.route('/servicos/lavagem')
def servico_lavagem():
    return render_template('servicos/lavagem.html', itens=SERVICOS_DETALHADOS['lavagem'])


@app.route('/servicos/estacionamento')
def servico_estacionamento():
    return render_template('servicos/estacionamento.html', itens=SERVICOS_DETALHADOS['estacionamento'])


@app.route('/esg')
def esg():
    return render_template('esg.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    tipo = request.args.get('tipo', 'cliente')
    erro = None

    if request.method == 'POST':
        tipo = request.form.get('tipo', 'cliente')
        identificador = request.form.get('cnpj', '').strip()
        senha = request.form.get('senha', '')
        logger_acesso.info(f'Tentativa de login - perfil={tipo}, ip={request.remote_addr}')

        if tipo in ['admin', 'funcionario']:
            with get_connection() as conexao:
                usuario = conexao.execute(
                    'SELECT * FROM usuarios WHERE nome = ? AND tipo = ? AND ativo = 1',
                    (identificador, tipo),
                ).fetchone()

            if usuario and senha_confere(usuario, senha):
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                session['tipo'] = usuario['tipo']
                return redirect(url_for(f'dashboard_{tipo}'))
            erro = 'Identificador ou senha incorretos para o acesso interno.'

        elif tipo == 'cliente':
            cnpj = somente_digitos(identificador)
            with get_connection() as conexao:
                usuario = conexao.execute(
                    "SELECT * FROM usuarios WHERE documento = ? AND tipo = 'cliente' AND ativo = 1",
                    (cnpj,),
                ).fetchone()

            if usuario and senha_confere(usuario, senha):
                cliente = fetch_one('SELECT cnpj, razao_social, email FROM cliente WHERE cnpj = %s', (cnpj,))
                if cliente:
                    session['usuario_id'] = usuario['id']
                    session['usuario_nome'] = cliente['razao_social']
                    session['usuario_identificador'] = cliente['cnpj']
                    session['tipo'] = 'cliente'
                    return redirect(url_for('dashboard_cliente'))
                erro = 'Cadastro local encontrado, mas o cliente nao existe no MySQL.'
            else:
                erro = 'CNPJ ou senha incorretos para a Area do Cliente.'

    return render_template('login.html', tipo=tipo, erro=erro)


@app.route('/redefinir-senha', methods=['GET', 'POST'])
def redefinir_senha():
    enviado = False
    erro = ''
    cnpj = ''
    email = ''
    email_mascarado = ''
    etapa = request.form.get('etapa', 'cnpj')

    if request.method == 'POST':
        cnpj = somente_digitos(request.form.get('cnpj'))
        cliente = fetch_one('SELECT cnpj, razao_social, email FROM cliente WHERE cnpj = %s', (cnpj,))

        if not cliente:
            erro = 'CNPJ nao localizado no cadastro de clientes.'
        else:
            email = cliente.get('email') or ''
            email_mascarado = mascarar_email(email)

            if etapa == 'confirmar':
                email_digitado = request.form.get('email_confirmacao', '').strip().lower()
                if email_digitado != email.lower():
                    erro = 'O e-mail digitado nao confere com o cadastro.'
                    etapa = 'confirmar'
                else:
                    enviado = True
                    etapa = 'concluido'
                    logger_auditoria.info(f'Redefinicao demonstrativa validada para {mascarar_cnpj(cnpj)}')
            else:
                etapa = 'confirmar'

    return render_template(
        'redefinir_senha.html',
        enviado=enviado,
        erro=erro,
        cnpj=cnpj,
        email=email,
        email_mascarado=email_mascarado,
        etapa=etapa,
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/contato', methods=['GET', 'POST'])
def contato():
    enviado = False
    erro_envio = ''
    aviso_envio = ''

    if request.method == 'POST':
        contato_dados = {
            'nome': request.form.get('nome', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telefone': request.form.get('telefone', '').strip(),
            'assunto': request.form.get('assunto', '').strip(),
            'mensagem': request.form.get('mensagem', '').strip(),
        }
        try:
            salvar_mensagem_contato(contato_dados)
            corpo = (
                'Nova mensagem pelo site Posto Nova Rota\n\n'
                f'Nome: {contato_dados["nome"]}\n'
                f'E-mail: {contato_dados["email"]}\n'
                f'Telefone: {contato_dados["telefone"]}\n'
                f'Assunto: {contato_dados["assunto"]}\n\n'
                f'{contato_dados["mensagem"]}'
            )
            aviso_envio = enviar_email(f'Contato - {contato_dados["assunto"]}', corpo)
            logger_auditoria.info(f'Contato recebido de {contato_dados["email"]}')
            enviado = True
        except Exception as exc:
            erro_envio = 'Erro ao salvar ou enviar mensagem.'
            logger_erro.exception(f'Erro contato: {exc}')

    return render_template(
        'contato.html',
        enviado=enviado,
        erro_envio=erro_envio,
        aviso_envio=aviso_envio,
        contato_enviado={},
        erros_validacao={},
    )


@app.route('/admin/dashboard', methods=['GET', 'POST'])
@login_obrigatorio('admin')
def dashboard_admin():
    mensagem = ''
    erro = ''
    painel_ativo = request.args.get('painel', 'dashboard')

    if request.method == 'POST':
        acoes = request.form.getlist('acao')
        acao = acoes[-1] if acoes else ''
        painel_ativo = request.form.get('painel', painel_ativo)
        try:
            if acao == 'salvar_servico':
                servico_id = request.form.get('servico_id')
                nome = request.form.get('nome', '').strip()
                descricao = request.form.get('descricao', '').strip()
                valor = Decimal(request.form.get('valor_unitario', '0').replace(',', '.'))
                desconto = Decimal(request.form.get('desconto', '0').replace(',', '.'))
                if servico_id:
                    execute_query(
                        'UPDATE `serviço_utilizado` SET nome=%s, descrição=%s, valor_unitario=%s, desconto=%s '
                        'WHERE `id_Serviço_utilizado`=%s',
                        (nome, descricao, valor, desconto, servico_id),
                    )
                    mensagem = 'Servico atualizado com sucesso.'
                    logger_auditoria.info(f'Admin editou servico id={servico_id} nome={nome}')
                else:
                    proximo = fetch_one(
                        'SELECT COALESCE(MAX(`id_Serviço_utilizado`), 0) + 1 AS id FROM `serviço_utilizado`'
                    )['id']
                    execute_query(
                        'INSERT INTO `serviço_utilizado` '
                        '(`id_Serviço_utilizado`, nome, descrição, valor_unitario, desconto) VALUES (%s, %s, %s, %s, %s)',
                        (proximo, nome, descricao, valor, desconto),
                    )
                    mensagem = 'Servico adicionado com sucesso.'
                    logger_auditoria.info(f'Admin criou servico id={proximo} nome={nome}')

            elif acao == 'excluir_servico':
                servico_id = request.form.get('servico_id')
                execute_query('DELETE FROM `serviço_utilizado` WHERE `id_Serviço_utilizado`=%s', (servico_id,))
                mensagem = 'Servico excluido com sucesso.'
                logger_auditoria.info(f'Admin excluiu servico id={servico_id}')

            elif acao == 'salvar_cliente':
                cnpj = somente_digitos(request.form.get('cnpj'))
                cnpj_original = somente_digitos(request.form.get('cnpj_original'))
                dados = (
                    request.form.get('razao_social', '').strip(),
                    somente_digitos(request.form.get('telefone')),
                    request.form.get('email', '').strip(),
                )
                veiculos = parse_veiculos_formulario(
                    request.form.get('placas'),
                    request.form.get('modelo_veiculo'),
                    request.form.get('ano_veiculo'),
                )
                if cnpj_original:
                    placa_principal = salvar_veiculos_cliente(cnpj_original, veiculos) if veiculos else None
                    campos = 'razao_social=%s, telefone=%s, email=%s'
                    valores = [*dados]
                    if placa_principal:
                        campos += ', Veiculo_placa_veiculo=%s'
                        valores.append(placa_principal)
                    valores.append(cnpj_original)
                    execute_query(
                        f'UPDATE cliente SET {campos} WHERE cnpj=%s',
                        tuple(valores),
                    )
                    mensagem = 'Cliente atualizado com sucesso.'
                    logger_auditoria.info(f'Admin editou cliente {mascarar_cnpj(cnpj_original)}')
                else:
                    placa = veiculos[0]['placa'] if veiculos else ''
                    if not veiculos:
                        erro = 'Informe pelo menos uma placa para adicionar o cliente.'
                    else:
                        for veiculo in veiculos:
                            execute_query(
                                'INSERT INTO veiculo (placa_veiculo, modelo, Ano_veiculo) VALUES (%s, %s, %s) '
                                'ON DUPLICATE KEY UPDATE modelo=VALUES(modelo), Ano_veiculo=VALUES(Ano_veiculo)',
                                (veiculo['placa'], veiculo['modelo'], veiculo['ano']),
                            )
                        execute_query(
                        'INSERT INTO cliente '
                        '(cnpj, razao_social, telefone, email, complemento, numero, `Endereço_cep`, '
                        'Veiculo_placa_veiculo, Fatura_id_Fatura) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)',
                        (
                            cnpj,
                            dados[0],
                            dados[1],
                            dados[2],
                            request.form.get('complemento', '').strip() or None,
                            request.form.get('numero') or None,
                            somente_digitos(request.form.get('cep')),
                            placa,
                        ),
                        )
                        salvar_veiculos_cliente(cnpj, veiculos)
                        mensagem = 'Cliente adicionado com sucesso.'
                        logger_auditoria.info(f'Admin criou cliente {mascarar_cnpj(cnpj)}')

            elif acao == 'excluir_cliente':
                cnpj = somente_digitos(request.form.get('cnpj'))
                execute_query('DELETE FROM cliente WHERE cnpj=%s', (cnpj,))
                mensagem = 'Cliente excluido com sucesso.'
                logger_auditoria.info(f'Admin excluiu cliente {mascarar_cnpj(cnpj)}')

            elif acao == 'salvar_boleto':
                boleto_id = request.form.get('boleto_id')
                vencimento = request.form.get('data_vencimento')
                emissao = request.form.get('data_emissao')
                codigo = request.form.get('codigo_barras', '').strip()
                status = request.form.get('status_pagamento', '').strip().upper()
                fatura_id = request.form.get('fatura_id')
                if boleto_id:
                    execute_query(
                        'UPDATE boleto SET data_vencimento=%s, data_emissao=%s, codigo_barras=%s, '
                        'status_pagamento=%s WHERE id_Boleto=%s',
                        (vencimento, emissao, codigo, status, boleto_id),
                    )
                    mensagem = 'Boleto atualizado com sucesso.'
                    logger_auditoria.info(f'Admin editou boleto id={boleto_id}')
                else:
                    execute_query(
                        'INSERT INTO boleto (data_vencimento, data_emissao, codigo_barras, status_pagamento, Fatura_id_Fatura) '
                        'VALUES (%s, %s, %s, %s, %s)',
                        (vencimento, emissao, codigo, status, fatura_id),
                    )
                    mensagem = 'Boleto adicionado com sucesso.'
                    logger_auditoria.info(f'Admin criou boleto fatura={fatura_id}')

            elif acao == 'excluir_boleto':
                boleto_id = request.form.get('boleto_id')
                execute_query('DELETE FROM boleto WHERE id_Boleto=%s', (boleto_id,))
                mensagem = 'Boleto excluido com sucesso.'
                logger_auditoria.info(f'Admin excluiu boleto id={boleto_id}')

            elif acao == 'gerar_boletos_mensais':
                cnpj = somente_digitos(request.form.get('cnpj'))
                competencia = request.form.get('competencia', '').strip()
                vencimento = request.form.get('vencimento') or (date.today() + timedelta(days=10)).isoformat()
                total_gerado = gerar_boletos_resumo_mensal(cnpj, competencia, vencimento)
                if total_gerado:
                    mensagem = f'{total_gerado} boleto(s) gerado(s) para o resumo mensal.'
                    logger_auditoria.info(
                        f'Admin gerou boletos mensais cliente={mascarar_cnpj(cnpj)} competencia={competencia} total={total_gerado}'
                    )
                else:
                    erro = 'Este resumo mensal nao possui faturas pendentes para gerar boleto.'
        except Exception as exc:
            erro = 'Nao foi possivel concluir a operacao. Verifique se ha registros vinculados.'
            logger_erro.exception(f'Erro admin: {exc}')

    cliente_busca = request.args.get('cliente_busca', '').strip()
    boleto_busca = request.args.get('boleto_busca', '').strip()
    servico_busca = request.args.get('servico_busca', '').strip()
    acesso_busca = request.args.get('acesso_busca', '').strip()
    faturamento_busca = request.args.get('faturamento_busca', '').strip()
    competencia = request.args.get('competencia', '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}', competencia or ''):
        competencia = ''

    clientes_total = fetch_one('SELECT COUNT(*) AS total FROM cliente')['total']
    resumo = porcentagem_status(resumo_boletos())
    resumo['clientes'] = clientes_total
    resumo['faturamento'] = faturamento_estimado()
    resumo['servicos'] = servicos_mais_utilizados()

    clientes_where = ''
    clientes_params = ()
    if cliente_busca:
        clientes_where = 'WHERE c.cnpj LIKE %s OR c.razao_social LIKE %s OR c.email LIKE %s'
        clientes_params = (f'%{cliente_busca}%', f'%{cliente_busca}%', f'%{cliente_busca}%')

    clientes = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, c.complemento, c.numero, c.`Endereço_cep` AS cep, '
        'c.Veiculo_placa_veiculo AS placa, v.modelo AS veiculo_modelo, v.Ano_veiculo AS veiculo_ano, '
        'c.Fatura_id_Fatura AS fatura_id, '
        '(SELECT GROUP_CONCAT(DISTINCT CONCAT(cv.placa_veiculo, '
        "CASE WHEN vv.modelo IS NOT NULL THEN CONCAT(' - ', vv.modelo) ELSE '' END) SEPARATOR ', ') "
        'FROM cliente_veiculo cv '
        'LEFT JOIN veiculo vv ON vv.placa_veiculo = cv.placa_veiculo '
        'WHERE cv.cliente_cnpj = c.cnpj) AS veiculos '
        'FROM cliente c '
        'LEFT JOIN veiculo v ON v.placa_veiculo = c.Veiculo_placa_veiculo '
        f'{clientes_where} ORDER BY c.razao_social LIMIT 30',
        clientes_params,
    )

    boletos_where = ''
    boletos_params = ()
    if boleto_busca:
        boletos_where = (
            'WHERE c.razao_social LIKE %s OR c.cnpj LIKE %s OR su.nome LIKE %s OR b.status_pagamento LIKE %s'
        )
        boletos_params = (f'%{boleto_busca}%', f'%{boleto_busca}%', f'%{boleto_busca}%', f'%{boleto_busca}%')
    boletos = listar_boletos(boletos_where, boletos_params, limite=30)
    faturas_disponiveis = listar_faturas_operacionais()
    resumos_mensais = listar_resumos_mensais(faturamento_busca, competencia)
    for resumo_mensal in resumos_mensais:
        resumo_mensal['itens'] = listar_itens_resumo_mensal(
            resumo_mensal['cnpj'],
            resumo_mensal['competencia'],
        )

    precos = carregar_precos_base()
    if servico_busca:
        termo = servico_busca.lower()
        precos = [
            servico for servico in precos
            if termo in str(servico.get('nome') or '').lower()
            or termo in str(servico.get('descricao') or '').lower()
        ]

    acessos = []
    log_path = BASE_DIR / 'logs' / 'acesso.log'
    if log_path.exists():
        acessos = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        if acesso_busca:
            acessos = [linha for linha in acessos if acesso_busca.lower() in linha.lower()]
        acessos = acessos[-12:]

    return render_template(
        'admin/dashboard_admin.html',
        usuario={'nome': session.get('usuario_nome')},
        resumo=resumo,
        precos=precos,
        clientes=clientes,
        boletos=boletos,
        faturas_disponiveis=faturas_disponiveis,
        boletos_pagos=boletos_por_status('PAGO'),
        boletos_abertos=boletos_por_status('EM ABERTO'),
        boletos_atrasados=boletos_por_status('ATRASADO'),
        acessos=acessos,
        filtros={
            'cliente_busca': cliente_busca,
            'boleto_busca': boleto_busca,
            'servico_busca': servico_busca,
            'acesso_busca': acesso_busca,
            'faturamento_busca': faturamento_busca,
            'competencia': competencia,
        },
        resumos_mensais=resumos_mensais,
        vencimento_padrao=(date.today() + timedelta(days=10)).isoformat(),
        painel_ativo=painel_ativo,
        mensagem=mensagem,
        erro=erro,
    )


@app.route('/funcionario/dashboard', methods=['GET', 'POST'])
@login_obrigatorio('funcionario')
def dashboard_funcionario():
    mensagem = ''
    erro = ''
    garantir_coluna_data_servico()

    if request.method == 'POST':
        cnpj = somente_digitos(request.form.get('cnpj'))
        placa_veiculo = ''.join(
            caractere for caractere in (request.form.get('placa_veiculo') or '').upper()
            if caractere.isalnum()
        )[:7]
        servico_id = request.form.get('tipo_servico')
        quantidade = Decimal(request.form.get('quantidade', '1').replace(',', '.'))
        data_registro = request.form.get('data_registro') or date.today().isoformat()
        try:
            cliente = fetch_one(
                'SELECT base.cnpj, base.razao_social, cv.placa_veiculo AS Veiculo_placa_veiculo '
                'FROM cliente base '
                'JOIN cliente_veiculo cv ON cv.cliente_cnpj = base.cnpj '
                'WHERE base.cnpj = %s AND cv.placa_veiculo = %s '
                'LIMIT 1',
                (cnpj, placa_veiculo),
            )
            if not cliente:
                erro = 'Cliente ou veículo não encontrado para registrar o serviço.'
            elif not placa_veiculo:
                erro = 'Selecione um veículo cadastrado para este cliente.'
            else:
                servico_registrado_id = execute_insert_id(
                    'INSERT INTO `serviço` '
                    '(qunt_utilizada, Serviço_utilizado_id_Serviço_utilizado, Veiculo_placa_veiculo, data_registro) '
                    'VALUES (%s, %s, %s, %s)',
                    (quantidade, servico_id, cliente['Veiculo_placa_veiculo'], data_registro),
                )
                proxima_fatura = fetch_one('SELECT COALESCE(MAX(id_Fatura), 0) + 1 AS id FROM fatura')['id']
                execute_query(
                    'INSERT INTO fatura (id_Fatura, Serviço_id_Serviço) VALUES (%s, %s)',
                    (proxima_fatura, servico_registrado_id),
                )
                mensagem = (
                    f'Servico registrado para {cliente["razao_social"]} '
                    f'no veículo {cliente["Veiculo_placa_veiculo"]}.'
                )
                logger_auditoria.info(
                    f'Funcionario registrou servico para {mascarar_cnpj(cnpj)} '
                    f'veiculo={cliente["Veiculo_placa_veiculo"]} data={data_registro}'
                )
        except Exception as exc:
            erro = 'Não foi possível registrar o serviço.'
            logger_erro.exception(f'Erro funcionario: {exc}')

    busca = request.args.get('cliente', '').strip()
    boleto_busca = request.args.get('boleto_busca', '').strip()
    boleto_status = request.args.get('boleto_status', '').strip().upper()
    faturamento_busca = request.args.get('faturamento_busca', '').strip()
    competencia = request.args.get('competencia', '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}', competencia or ''):
        competencia = ''
    if boleto_status not in {'PAGO', 'EM ABERTO', 'ATRASADO'}:
        boleto_status = ''
    params = ()
    where = ''
    if busca:
        where = 'WHERE c.razao_social LIKE %s'
        params = (f'%{busca}%',)

    clientes = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, c.Veiculo_placa_veiculo AS placa, '
        'v.modelo AS veiculo_modelo, v.Ano_veiculo AS veiculo_ano, '
        'COUNT(b.id_Boleto) AS total_boletos, '
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'EM ABERTO' THEN 1 ELSE 0 END) AS boletos_abertos "
        'FROM cliente c '
        'LEFT JOIN veiculo v ON v.placa_veiculo = c.Veiculo_placa_veiculo '
        'LEFT JOIN fatura f ON f.id_Fatura = c.Fatura_id_Fatura '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where} '
        'GROUP BY c.cnpj, c.razao_social, c.telefone, c.email, c.Veiculo_placa_veiculo, v.modelo, v.Ano_veiculo '
        'ORDER BY c.razao_social',
        params,
    )
    for cliente in clientes:
        cliente['cnpj_mascarado'] = mascarar_cnpj(cliente['cnpj'])

    clientes_registro = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.Veiculo_placa_veiculo AS placa, '
        'v.modelo AS veiculo_modelo, v.Ano_veiculo AS veiculo_ano '
        'FROM cliente c '
        'LEFT JOIN veiculo v ON v.placa_veiculo = c.Veiculo_placa_veiculo '
        'ORDER BY c.razao_social'
    )
    todos_veiculos_cliente = fetch_all(
        'SELECT c.cnpj, c.razao_social, cv.placa_veiculo AS placa, '
        'v.modelo AS veiculo_modelo, v.Ano_veiculo AS veiculo_ano '
        'FROM cliente c '
        'JOIN cliente_veiculo cv ON cv.cliente_cnpj = c.cnpj '
        'LEFT JOIN veiculo v ON v.placa_veiculo = cv.placa_veiculo '
        'ORDER BY c.razao_social, cv.placa_veiculo'
    )
    for cliente in clientes_registro:
        veiculos = []
        vistos = set()
        for veiculo in todos_veiculos_cliente:
            if veiculo.get('cnpj') != cliente.get('cnpj'):
                continue
            placa = veiculo.get('placa')
            if not placa or placa in vistos:
                continue
            vistos.add(placa)
            partes = [placa]
            if veiculo.get('veiculo_modelo'):
                partes.append(str(veiculo['veiculo_modelo']))
            if veiculo.get('veiculo_ano'):
                partes.append(str(veiculo['veiculo_ano']))
            veiculos.append({'placa': placa, 'rotulo': ' - '.join(partes)})
        cliente['veiculos'] = veiculos

    resumo = porcentagem_status(resumo_boletos())
    boleto_condicoes = []
    boleto_params = []
    if boleto_busca:
        boleto_condicoes.append('(c.razao_social LIKE %s OR su.nome LIKE %s)')
        boleto_params.extend([f'%{boleto_busca}%', f'%{boleto_busca}%'])
    if boleto_status:
        boleto_condicoes.append('UPPER(b.status_pagamento) = %s')
        boleto_params.append(boleto_status)
    boletos_where = ''
    if boleto_condicoes:
        boletos_where = 'WHERE ' + ' AND '.join(boleto_condicoes)
    painel_ativo = 'visao-geral'
    if busca:
        painel_ativo = 'clientes'
    if boleto_busca or boleto_status:
        painel_ativo = 'boletos'
    if faturamento_busca or competencia:
        painel_ativo = 'faturamento'
    if request.method == 'POST':
        painel_ativo = 'registrar-servico'

    return render_template(
        'funcionario/dashboard_funcionario.html',
        usuario={'nome': session.get('usuario_nome')},
        resumo=resumo,
        clientes=clientes,
        boletos=listar_boletos(boletos_where, tuple(boleto_params), limite=30),
        boletos_pagos=boletos_por_status('PAGO'),
        boletos_abertos=boletos_por_status('EM ABERTO'),
        boletos_atrasados=boletos_por_status('ATRASADO'),
        precos=carregar_precos_base(),
        clientes_registro=clientes_registro,
        resumos_mensais=listar_resumos_mensais(faturamento_busca, competencia),
        hoje=date.today().isoformat(),
        busca=busca,
        boleto_busca=boleto_busca,
        boleto_status=boleto_status,
        faturamento_busca=faturamento_busca,
        competencia=competencia,
        painel_ativo=painel_ativo,
        mensagem=mensagem,
        erro=erro,
    )


@app.route('/cliente/dashboard')
@login_obrigatorio('cliente')
def dashboard_cliente():
    cnpj = session.get('usuario_identificador')
    periodo_chave = request.args.get('periodo', '90')
    if periodo_chave not in PERIODOS_CLIENTE:
        periodo_chave = '90'
    periodo = PERIODOS_CLIENTE[periodo_chave]

    where_boletos = 'WHERE c.cnpj = %s'
    where_servicos = 'WHERE c.cnpj = %s'
    if periodo['dias']:
        where_boletos += f' AND b.data_vencimento >= DATE_SUB(CURDATE(), INTERVAL {periodo["dias"]} DAY)'
        where_servicos += f' AND (b.data_vencimento IS NULL OR b.data_vencimento >= DATE_SUB(CURDATE(), INTERVAL {periodo["dias"]} DAY))'

    boletos = listar_boletos(where_boletos, (cnpj,), limite=30)
    boleto_aberto = next((b for b in boletos if str(b['status_pagamento']).upper() == 'EM ABERTO'), None)
    servicos_cliente = fetch_all(
        'SELECT DISTINCT s.id_Serviço AS servico_id, su.nome, su.descrição AS descricao, '
        'su.valor_unitario, su.desconto, s.qunt_utilizada, s.data_registro '
        'FROM cliente c '
        'JOIN cliente_veiculo cv ON cv.cliente_cnpj = c.cnpj '
        'JOIN `serviço` s ON s.Veiculo_placa_veiculo = cv.placa_veiculo '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.Serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN fatura f ON f.Serviço_id_Serviço = s.id_Serviço '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where_servicos} ORDER BY s.id_Serviço DESC LIMIT 30',
        (cnpj,),
    )
    resumo_cliente = calcular_resumo_cliente(servicos_cliente, boletos)
    return render_template(
        'cliente/dashboard_cliente.html',
        usuario={'nome': session.get('usuario_nome'), 'identificador': cnpj},
        boletos=boletos,
        boleto_aberto=boleto_aberto,
        servicos=servicos_cliente,
        resumo=resumo_cliente,
        periodo_atual=periodo_chave,
        periodo_label=periodo['label'],
        periodos=PERIODOS_CLIENTE,
    )


@app.errorhandler(404)
def not_found(_):
    return render_template('erro.html', erro='Pagina nao encontrada'), 404


@app.errorhandler(500)
def internal_error(_):
    logger_erro.exception('Erro interno do servidor')
    return render_template('erro.html', erro='Erro interno do servidor'), 500


if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', '8001')),
    )
