# Garante que o navegador receba arquivos CSS com o tipo MIME correto.
import mimetypes
mimetypes.add_type('text/css', '.css')

# Bibliotecas usadas para relatórios, backups, datas, e-mail e utilitários gerais.
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


# Caminho base do projeto; tudo que depende de arquivo local parte daqui.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

# Instância principal do Flask, apontando explicitamente para static/ e templates/.
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / 'static'),
    static_url_path='/static',
    template_folder=str(BASE_DIR / 'templates'),
)

# A chave secreta protege sessão, cookies e tokens CSRF.
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError('SECRET_KEY nao configurada no .env!')

# Desativa cache padrão de arquivos enviados pelo Flask em ambiente de desenvolvimento.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Proteção contra envio malicioso de formulários por sites externos.
csrf = CSRFProtect(app)

# Inicializa o banco local usado para usuários, mensagens e dados auxiliares.
init_db()


# Catálogo fixo usado nas páginas públicas detalhadas de serviços.
SERVICOS_DETALHADOS = {
    'combustivel': [
        {
            'nome': 'Gasolina comum',
            'preco': Decimal('5.49'),
            'unidade': 'litro',
            'descricao': 'Combustível de boa estabilidade para uso diário, com controle de qualidade e rendimento equilibrado.',
        },
        {
            'nome': 'Gasolina aditivada',
            'preco': Decimal('5.79'),
            'unidade': 'litro',
            'descricao': 'Contém aditivos detergentes e dispersantes que ajudam a manter bicos, válvulas e câmara de combustão mais limpos.',
        },
        {
            'nome': 'Etanol',
            'preco': Decimal('3.89'),
            'unidade': 'litro',
            'descricao': 'Etanol hidratado de alta qualidade, com queima mais limpa, boa resposta do motor e origem renovável.',
        },
        {
            'nome': 'Diesel S10',
            'preco': Decimal('6.09'),
            'unidade': 'litro',
            'descricao': 'Diesel com baixo teor de enxofre, indicado para motores modernos e para uma operação mais eficiente da frota.',
        },
    ],
    'lavagem': [
        {
            'nome': 'Lavagem simples',
            'preco': Decimal('25.00'),
            'unidade': 'serviço',
            'descricao': 'Limpeza externa rápida para remover poeira, marcas do uso diário e renovar a apresentação do veículo.',
        },
        {
            'nome': 'Lavagem completa',
            'preco': Decimal('35.00'),
            'unidade': 'serviço',
            'descricao': 'Cuidado externo e interno, com atenção a rodas, vidros, painel e acabamento geral.',
        },
        {
            'nome': 'Higienização interna',
            'preco': Decimal('60.00'),
            'unidade': 'serviço',
            'descricao': 'Processo focado em bancos, tapetes e superfícies internas para mais conforto e sensação de limpeza.',
        },
        {
            'nome': 'Acabamento especial',
            'preco': Decimal('45.00'),
            'unidade': 'serviço',
            'descricao': 'Finalização com brilho e proteção visual para valorizar a pintura e melhorar a aparência do veículo.',
        },
    ],
    'estacionamento': [
        {
            'nome': 'Estacionamento rotativo',
            'preco': Decimal('8.00'),
            'unidade': 'hora',
            'descricao': 'Ideal para paradas curtas, com controle de entrada e saída para mais praticidade.',
        },
        {
            'nome': 'Diária',
            'preco': Decimal('35.00'),
            'unidade': 'dia',
            'descricao': 'Opção para quem precisa deixar o veículo por mais tempo com previsibilidade de custo.',
        },
        {
            'nome': 'Estacionamento mensal',
            'preco': Decimal('150.00'),
            'unidade': 'mês',
            'descricao': 'Plano recorrente para empresas e frotas, facilitando controle e faturamento.',
        },
    ],
}


def brl(valor):
    """Formata valores numericos no padrao monetario brasileiro."""
    try:
        numero = Decimal(str(valor or 0))
    except Exception:
        numero = Decimal('0')
    texto = f'{numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {texto}'


app.jinja_env.filters['brl'] = brl


@app.context_processor
def inject_globals():
    """Disponibiliza variaveis globais para todos os templates."""
    return {'current_year': datetime.now().year}


@app.after_request
def no_cache(response):
    """Impede que paginas dinamicas fiquem presas no cache do navegador."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def somente_digitos(valor):
    """Remove tudo que nao for numero, util para CNPJ, telefone e CEP."""
    return re.sub(r'\D', '', str(valor or ''))


def normalizar_placa(valor):
    """Padroniza placa em maiusculas, sem separadores e com ate 7 caracteres."""
    return ''.join(caractere for caractere in (valor or '').upper() if caractere.isalnum())[:7]


def parse_veiculos_formulario(texto, modelo_padrao='', ano_padrao=''):
    """Converte um campo de texto livre em uma lista estruturada de veiculos."""
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


def parse_veiculos_request(formulario):
    """Le placas, modelos e anos vindos dos campos repetidos do formulario."""
    placas = formulario.getlist('placa_veiculo')
    modelos = formulario.getlist('modelo_veiculo')
    anos = formulario.getlist('ano_veiculo')
    if not placas and formulario.get('placas'):
        return parse_veiculos_formulario(
            formulario.get('placas'),
            formulario.get('modelo_veiculo'),
            formulario.get('ano_veiculo'),
        )

    veiculos = []
    vistos = set()
    for indice, placa_bruta in enumerate(placas):
        placa = normalizar_placa(placa_bruta)
        if not placa or placa in vistos:
            continue
        modelo = (modelos[indice] if indice < len(modelos) else '').strip() or 'Não informado'
        ano_texto = somente_digitos(anos[indice] if indice < len(anos) else '')
        ano = int(ano_texto or date.today().year)
        veiculos.append({'placa': placa, 'modelo': modelo[:28], 'ano': ano})
        vistos.add(placa)
    return veiculos


def mascarar_cnpj(cnpj):
    """Oculta parte do CNPJ para uso seguro em logs e mensagens."""
    digitos = somente_digitos(cnpj)
    if len(digitos) != 14:
        return 'CNPJ protegido'
    return f'**.***.***/{digitos[8:12]}-{digitos[12:]}'


def mascarar_email(email):
    """Oculta parte do e-mail sem perder a referencia do dominio."""
    if not email or '@' not in email:
        return 'e-mail nao cadastrado'
    local, dominio = email.split('@', 1)
    if len(local) <= 4:
        local_mascarado = f'{local[:1]}***{local[-1:]}'
    else:
        local_mascarado = f'{local[:2]}***{local[-2:]}'
    return f'{local_mascarado}@{dominio}'


def senha_armazenada_e_hash(valor):
    """Identifica se a senha ja esta salva como hash do Werkzeug."""
    return str(valor or '').startswith(('pbkdf2:', 'scrypt:'))


def senha_confere(usuario, senha):
    """Compara a senha digitada com hash moderno ou senha antiga em texto."""
    senha_armazenada = usuario['senha'] if usuario else ''
    if senha_armazenada_e_hash(senha_armazenada):
        return check_password_hash(senha_armazenada, senha)
    return senha_armazenada == senha


def senha_forte(senha):
    """Valida a politica minima de senha forte usada na migracao."""
    return bool(
        senha
        and len(senha) >= 8
        and re.search(r'[A-Z]', senha)
        and re.search(r'[a-z]', senha)
        and re.search(r'\d', senha)
        and re.search(r'[^A-Za-z0-9]', senha)
    )


# Senhas temporarias usadas apenas para migrar usuarios legados para hash.
SENHAS_PADRAO_FORTES = {
    ('admin', 'Administrador'): 'Admin@123',
    ('funcionario', 'João Silva'): 'Func@1234',
    ('funcionario', 'Joao Silva'): 'Func@1234',
    ('cliente', 'Alemanha Transportes SA'): 'Cliente@123',
    ('cliente', 'Empresa Exemplo Ltda'): 'Cliente@123',
}


def migrar_senhas_para_hash():
    """Atualiza senhas antigas do SQLite para hashes seguros."""
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
    """Converte datas do banco para formato brasileiro legivel."""
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
    """Prepara registros para exportacao, convertendo valores para texto."""
    return {
        chave: data_hora_br(valor) if isinstance(valor, (date, datetime)) else str(valor or '')
        for chave, valor in dict(linha).items()
    }


def resposta_csv(nome_arquivo, secoes):
    """Gera uma resposta HTTP de download contendo relatorio em CSV."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=';')
    escritor.writerow(['Posto Nova Rota'])
    escritor.writerow(['Relatório gerado em', datetime.now().strftime('%d/%m/%Y %H:%M')])
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
    """Escapa caracteres especiais antes de inserir texto no PDF manual."""
    return str(texto).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def resposta_pdf(nome_arquivo, secoes):
    """Gera uma resposta HTTP de download contendo relatorio em PDF simples."""
    def texto_pdf(comandos, x, y, texto, tamanho=10, fonte='F1', cor=(0.06, 0.13, 0.24)):
        """Adiciona um comando de texto na pagina PDF em construcao."""
        r, g, b = cor
        comandos.append(f'{r:.3f} {g:.3f} {b:.3f} rg')
        comandos.append('BT')
        comandos.append(f'/{fonte} {tamanho} Tf')
        comandos.append(f'{x} {y} Td')
        comandos.append(f'({escapar_pdf(texto)}) Tj')
        comandos.append('ET')

    def retangulo_pdf(comandos, x, y, largura, altura, cor):
        """Desenha retangulos coloridos usados como cabecalhos e cards."""
        r, g, b = cor
        comandos.append(f'{r:.3f} {g:.3f} {b:.3f} rg')
        comandos.append(f'{x} {y} {largura} {altura} re f')

    def quebrar_texto(texto, limite=92):
        """Quebra textos longos para caberem na largura disponivel do PDF."""
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

    def nova_pagina(subtitulo='Relatório executivo'):
        """Cria uma nova pagina com cabecalho padronizado."""
        nonlocal comandos, y, numero_pagina
        if comandos:
            paginas.append(comandos)
        numero_pagina += 1
        comandos = []
        retangulo_pdf(comandos, 0, 782, 595, 60, (0.05, 0.12, 0.22))
        retangulo_pdf(comandos, 0, 774, 595, 8, (0.04, 0.45, 0.78))
        texto_pdf(comandos, 40, 808, 'Posto Nova Rota', 20, 'F2', (1, 1, 1))
        texto_pdf(comandos, 40, 790, subtitulo, 10, 'F1', (0.88, 0.94, 1))
        texto_pdf(comandos, 420, 790, f'Página {numero_pagina}', 9, 'F1', (0.88, 0.94, 1))
        y = 738

    def garantir_espaco(altura):
        """Abre nova pagina quando o proximo bloco nao cabe na atual."""
        nonlocal y
        if y - altura < 52:
            nova_pagina('Continuação do relatório')

    nova_pagina('Relatório executivo')
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


RELATORIOS_DATA_INICIAL = datetime.strptime(
    os.getenv('RELATORIOS_DATA_INICIAL', '2026-05-30'),
    '%Y-%m-%d',
).date()


def adicionar_filtro_relatorio(where, condicao, params=None):
    """Acrescenta um filtro temporal sem duplicar WHERE nas consultas."""
    conector = ' AND ' if where.strip() else 'WHERE '
    return f'{where}{conector}{condicao}', tuple(params or ()) + (RELATORIOS_DATA_INICIAL,)


def relatorio_servicos(where='', params=None, incluir_cnpj=True):
    """Lista servicos prestados para compor relatorios por perfil."""
    where, params = adicionar_filtro_relatorio(where, 's.data_registro >= %s', params)
    colunas_cliente = 'c.razao_social AS cliente, c.cnpj, ' if incluir_cnpj else 'c.razao_social AS cliente, '
    linhas = fetch_all(
        'SELECT s.id_Serviço AS id, s.data_registro AS data, '
        f'{colunas_cliente}'
        's.Veiculo_placa_veiculo AS placa, su.nome AS servico, s.qunt_utilizada AS quantidade, '
        'su.valor_unitario, su.desconto '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN fatura f ON f.serviço_id_Serviço = s.id_Serviço '
        'LEFT JOIN cliente c ON c.cnpj = f.cliente_cnpj '
        f'{where} ORDER BY s.id_Serviço DESC LIMIT 500',
        params,
    )
    return [normalizar_linha_relatorio(linha) for linha in linhas]


def boletos_relatorio(where='', params=None, limite=500):
    """Reaproveita a listagem de boletos em formato pronto para relatorio."""
    where, params = adicionar_filtro_relatorio(where, 'b.data_emissao >= %s', params)
    return [normalizar_linha_relatorio(linha) for linha in listar_boletos(where, params, limite=limite)]


def eventos_auditoria(*termos):
    """Busca eventos do log de auditoria que contenham todos os termos informados."""
    log_path = BASE_DIR / 'logs' / 'auditoria.log'
    if not log_path.exists():
        return []
    eventos = []
    termos_normalizados = [termo.lower() for termo in termos]
    for linha in log_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        try:
            data_evento = datetime.strptime(linha[1:11], '%d/%m/%Y').date()
        except ValueError:
            continue
        if data_evento < RELATORIOS_DATA_INICIAL:
            continue
        texto = linha.lower()
        if all(termo in texto for termo in termos_normalizados):
            eventos.append({'evento': linha})
    return eventos[-80:]


def relatorio_admin():
    """Monta todas as secoes que o administrador pode exportar."""
    clientes = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, '
        '(SELECT GROUP_CONCAT(v.placa_veiculo SEPARATOR ", ") FROM veiculo v WHERE v.cliente_cnpj = c.cnpj) AS placas '
        'FROM cliente c ORDER BY c.razao_social LIMIT 500'
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
        ('Serviços prestados', relatorio_servicos()),
        ('Novos serviços cadastrados', eventos_auditoria('criou', 'servico')),
        ('Serviços atualizados', eventos_auditoria('editou', 'servico')),
        ('Novas vendas registradas', eventos_auditoria('registrou servico')),
    ]


def relatorio_funcionario():
    """Monta o relatorio operacional permitido para funcionarios."""
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
        ('Serviços prestados', relatorio_servicos(incluir_cnpj=False)),
        ('Vendas registradas pela equipe', eventos_auditoria('registrou servico')),
    ]


def relatorio_cliente(cnpj):
    """Monta o relatorio individual de um cliente especifico."""
    where_boletos, params_boletos = adicionar_filtro_relatorio(
        'WHERE c.cnpj = %s',
        'b.data_emissao >= %s',
        (cnpj,),
    )
    boletos = listar_boletos(where_boletos, params_boletos, limite=500)
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
        ('Meus serviços utilizados', servicos),
    ]


def criar_backup_automatico():
    """Copia o SQLite e exporta tabelas MySQL para arquivos de backup."""
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
    """Verifica se ja passou o intervalo de 24 horas desde o ultimo backup."""
    marcador = BASE_DIR / 'backups' / 'ultimo_backup.txt'
    if not marcador.exists():
        return True
    try:
        ultimo = datetime.fromisoformat(marcador.read_text(encoding='utf-8').strip())
        return datetime.now() - ultimo >= timedelta(hours=24)
    except Exception:
        return True


def rotina_backup_24h():
    """Executa em thread separada, checando periodicamente se precisa backup."""
    while True:
        try:
            if backup_esta_vencido():
                criar_backup_automatico()
        except Exception as exc:
            logger_erro.exception(f'Erro na rotina de backup: {exc}')
        time.sleep(3600)


def iniciar_backup_automatico():
    """Dispara o backup inicial e agenda a rotina em segundo plano."""
    if backup_esta_vencido():
        criar_backup_automatico()
    thread = threading.Thread(target=rotina_backup_24h, daemon=True)
    thread.start()


def coluna_existe(tabela, coluna):
    """Consulta o INFORMATION_SCHEMA para saber se uma coluna existe no MySQL."""
    row = fetch_one(
        'SELECT COUNT(*) AS total '
        'FROM INFORMATION_SCHEMA.COLUMNS '
        'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s',
        (tabela, coluna),
    )
    return bool(row and row.get('total'))


def validar_modelo_mysql():
    """Falha cedo quando o schema conectado nao corresponde ao DER esperado."""
    colunas_obrigatorias = {
        'cliente': ('cnpj', 'Endereço_cep'),
        'veiculo': ('placa_veiculo', 'cliente_cnpj'),
        'serviço': (
            'id_Serviço',
            'serviço_utilizado_id_Serviço_utilizado',
            'Veiculo_placa_veiculo',
            'data_registro',
        ),
        'fatura': ('id_Fatura', 'serviço_id_Serviço', 'cliente_cnpj'),
        'boleto': ('id_Boleto', 'Fatura_id_Fatura', 'status_pagamento'),
    }
    ausentes = [
        f'{tabela}.{coluna}'
        for tabela, colunas in colunas_obrigatorias.items()
        for coluna in colunas
        if not coluna_existe(tabela, coluna)
    ]
    if ausentes:
        raise RuntimeError(f'Schema MySQL incompatível. Colunas ausentes: {", ".join(ausentes)}')


# Rotinas executadas na inicializacao para preparar senhas, banco e backup.
migrar_senhas_para_hash()
validar_modelo_mysql()
iniciar_backup_automatico()


def login_obrigatorio(*perfis):
    """Decorator que restringe rotas aos perfis informados."""
    def decorator(func):
        """Recebe a funcao da rota que sera protegida."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            """Valida o perfil em sessao antes de executar a rota."""
            if session.get('tipo') not in perfis:
                return redirect(url_for('login', tipo=perfis[0] if perfis else 'cliente'))
            return func(*args, **kwargs)
        return wrapper
    return decorator


@app.route('/relatorios/<perfil>/<formato>')
@login_obrigatorio('admin', 'funcionario', 'cliente')
def exportar_relatorio(perfil, formato):
    """Exporta relatorios em CSV ou PDF respeitando o perfil logado."""
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
    """Envia e-mail via SMTP usando as configuracoes do arquivo .env."""
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
    """Carrega a tabela de servicos/precos cadastrada no MySQL."""
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
    """Calcula totais de boletos por status para os cards dos dashboards."""
    query = (
        'SELECT '
        'COUNT(*) AS total_boletos, '
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'PAGO' THEN 1 ELSE 0 END) AS boletos_pagos, "
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'EM ABERTO' THEN 1 ELSE 0 END) AS boletos_abertos, "
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'ATRASADO' THEN 1 ELSE 0 END) AS boletos_atrasados "
        'FROM boleto b '
        'JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN cliente c ON c.cnpj = f.cliente_cnpj '
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
    """Lista boletos com dados de cliente, veiculo e servico relacionado."""
    query = (
        'SELECT b.id_Boleto, b.data_vencimento, b.data_emissao, b.codigo_barras, b.status_pagamento, '
        'c.razao_social, c.cnpj, s.Veiculo_placa_veiculo AS placa_veiculo, '
        'su.nome AS servico, su.valor_unitario, su.desconto '
        'FROM boleto b '
        'JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN cliente c ON c.cnpj = f.cliente_cnpj '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
        f'{where} '
        'ORDER BY b.data_vencimento DESC '
        f'LIMIT {int(limite)}'
    )
    return fetch_all(query, params or ())


def faturamento_estimado():
    """Soma o valor estimado de todos os servicos registrados."""
    row = fetch_one(
        'SELECT SUM(s.qunt_utilizada * GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0)) AS total '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado'
    )
    return row.get('total') or Decimal('0')


def servicos_mais_utilizados():
    """Agrupa servicos por popularidade para exibir graficos/resumos."""
    rows = fetch_all(
        'SELECT su.nome, COUNT(*) AS total '
        'FROM `serviço` s '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
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


# Periodos disponiveis para filtrar o historico no dashboard do cliente.
PERIODOS_CLIENTE = {
    '30': {'label': 'Últimos 30 dias', 'dias': 30},
    '90': {'label': 'Últimos 90 dias', 'dias': 90},
    '180': {'label': 'Últimos 6 meses', 'dias': 180},
    '365': {'label': 'Últimos 12 meses', 'dias': 365},
    'todos': {'label': 'Todo o histórico', 'dias': None},
}


def decimal_seguro(valor):
    """Converte valores para Decimal sem quebrar quando vierem vazios."""
    try:
        return Decimal(str(valor or 0))
    except Exception:
        return Decimal('0')


def gerar_codigo_barras_demonstracao(fatura_id):
    """Gera um codigo de barras ficticio para boletos demonstrativos."""
    base = f'23790{date.today().strftime("%Y%m%d")}{int(fatura_id):031d}'
    return somente_digitos(base)[:44].ljust(44, '0')


def criar_boleto_para_fatura(fatura_id, vencimento=None, status='EM ABERTO'):
    """Cria boleto para uma fatura, evitando duplicidade."""
    boleto = fetch_one(
        'SELECT id_Boleto FROM boleto WHERE Fatura_id_Fatura=%s',
        (fatura_id,),
    )
    if boleto:
        return None

    vencimento = vencimento or (date.today() + timedelta(days=10)).isoformat()
    execute_query(
        'INSERT INTO boleto (data_vencimento, data_emissao, codigo_barras, status_pagamento, Fatura_id_Fatura) '
        'VALUES (%s, %s, %s, %s, %s)',
        (vencimento, date.today().isoformat(), gerar_codigo_barras_demonstracao(fatura_id), status, fatura_id),
    )
    return fatura_id


def listar_resumos_mensais(cliente_busca='', competencia='', limite=24):
    """Agrupa faturamento mensal por cliente e competencia."""
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
        'JOIN fatura f ON f.cliente_cnpj = c.cnpj '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where} '
        'GROUP BY c.cnpj, c.razao_social, DATE_FORMAT(s.data_registro, %s) '
        'ORDER BY competencia DESC, c.razao_social '
        f'LIMIT {int(limite)}',
        ('%Y-%m', '%m/%Y', *params, '%Y-%m'),
    )


def listar_itens_resumo_mensal(cnpj, competencia):
    """Detalha cada lancamento que forma o extrato mensal de um cliente."""
    return fetch_all(
        'SELECT s.id_Serviço AS id_servico, s.data_registro, '
        's.Veiculo_placa_veiculo AS placa_veiculo, su.nome AS servico, '
        's.qunt_utilizada AS quantidade, '
        'GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0) AS valor_unitario, '
        's.qunt_utilizada * GREATEST(su.valor_unitario - COALESCE(su.desconto, 0), 0) AS subtotal, '
        'COALESCE(b.status_pagamento, %s) AS status_pagamento '
        'FROM fatura f '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        'WHERE f.cliente_cnpj = %s AND DATE_FORMAT(s.data_registro, %s) = %s '
        'ORDER BY s.data_registro, s.id_Serviço',
        ('SEM BOLETO', cnpj, '%Y-%m', competencia),
    )

def calcular_resumo_cliente(servicos, boletos):
    """Calcula totais e indicadores exibidos na area do cliente."""
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
        nome = servico.get('nome') or 'Serviço'
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
    """Adiciona percentuais de status ao dicionario de resumo de boletos."""
    total = int(resumo.get('total_boletos') or 0) or 1
    pago = int(resumo.get('boletos_pagos') or 0)
    aberto = int(resumo.get('boletos_abertos') or 0)
    resumo['pct_pago'] = round((pago / total) * 100, 2)
    resumo['pct_aberto'] = round(((pago + aberto) / total) * 100, 2)
    return resumo


def boletos_por_status(status, limite=6):
    """Busca uma pequena lista de boletos filtrados por status."""
    return listar_boletos(
        'WHERE UPPER(b.status_pagamento) = %s',
        (status.upper(),),
        limite=limite,
    )


def garantir_coluna_data_servico():
    """Confere se a coluna data_registro existe na tabela de servicos."""
    try:
        coluna = fetch_one("SHOW COLUMNS FROM `serviço` LIKE 'data_registro'")
        if not coluna:
            logger_erro.error('Coluna data_registro nao encontrada na tabela servico.')
    except Exception as exc:
        logger_erro.exception(f'Nao foi possivel verificar data_registro em servico: {exc}')


def classe_status(status):
    """Traduz o status do boleto para uma classe CSS usada nos templates."""
    status_normalizado = str(status or '').strip().upper()
    if status_normalizado == 'PAGO':
        return 'paid'
    if status_normalizado == 'ATRASADO':
        return 'late'
    return 'open'


app.jinja_env.globals['classe_status'] = classe_status


def fatura_mais_recente_por_placa(placa):
    """Encontra a fatura mais recente vinculada a uma placa."""
    placa = (placa or '').strip().upper()
    if not placa:
        return None
    row = fetch_one(
        'SELECT f.id_Fatura AS id '
        'FROM fatura f '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'WHERE s.Veiculo_placa_veiculo = %s '
        'ORDER BY f.id_Fatura DESC LIMIT 1',
        (placa,),
    )
    return row.get('id') if row else None


def listar_faturas_operacionais(limite=200, somente_sem_boleto=False):
    """Lista faturas recentes, opcionalmente apenas as que nao tem boleto."""
    where = 'WHERE b.id_Boleto IS NULL ' if somente_sem_boleto else ''
    return fetch_all(
        'SELECT f.id_Fatura AS id, c.razao_social, c.cnpj, s.Veiculo_placa_veiculo AS placa, '
        'su.nome AS servico, s.data_registro, b.id_Boleto AS boleto_id '
        'FROM fatura f '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
        'LEFT JOIN cliente c ON c.cnpj = f.cliente_cnpj '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where}'
        'ORDER BY f.id_Fatura DESC LIMIT %s',
        (int(limite),),
    )


def cliente_bloqueado_por_inadimplencia(cnpj):
    """Verifica se o cliente possui boleto vencido ha mais de dois meses."""
    cnpj = somente_digitos(cnpj)
    if not cnpj:
        return None
    return fetch_one(
        'SELECT b.id_Boleto, b.data_vencimento, b.status_pagamento, c.razao_social '
        'FROM boleto b '
        'JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN cliente c ON c.cnpj = f.cliente_cnpj '
        'WHERE c.cnpj = %s '
        "AND UPPER(b.status_pagamento) <> 'PAGO' "
        'AND b.data_vencimento < DATE_SUB(CURDATE(), INTERVAL 2 MONTH) '
        'ORDER BY b.data_vencimento ASC LIMIT 1',
        (cnpj,),
    )


def salvar_veiculos_cliente(cnpj, veiculos):
    """Insere ou atualiza os veiculos associados a um cliente."""
    if not veiculos:
        raise ValueError('Informe pelo menos uma placa para o cliente.')
    for veiculo in veiculos:
        execute_query(
            'INSERT INTO veiculo (placa_veiculo, cliente_cnpj, modelo, Ano_veiculo) VALUES (%s, %s, %s, %s) '
            'ON DUPLICATE KEY UPDATE cliente_cnpj=VALUES(cliente_cnpj), modelo=VALUES(modelo), Ano_veiculo=VALUES(Ano_veiculo)',
            (veiculo['placa'], cnpj, veiculo['modelo'], veiculo['ano']),
        )
    return veiculos[0]['placa']


def validar_dados_cliente(cnpj, dados, veiculos, cep=None):
    """Valida limites do DER antes de iniciar o cadastro administrativo."""
    razao_social, telefone, email = dados
    if len(cnpj) != 14:
        raise ValueError('Informe um CNPJ com 14 dígitos.')
    if not razao_social:
        raise ValueError('Informe a razão social do cliente.')
    if len(razao_social) > 30:
        raise ValueError('A razão social deve ter no máximo 30 caracteres.')
    if len(telefone) > 11:
        raise ValueError('O telefone deve ter no máximo 11 dígitos.')
    if len(email) > 30:
        raise ValueError('O e-mail deve ter no máximo 30 caracteres.')
    if not veiculos:
        raise ValueError('Informe pelo menos uma placa para o cliente.')
    for veiculo in veiculos:
        if len(veiculo['placa']) != 7:
            raise ValueError('Cada placa deve possuir 7 caracteres.')
        if len(veiculo['modelo']) > 28:
            raise ValueError('O modelo do veículo deve ter no máximo 28 caracteres.')
    if cep is not None:
        if len(cep) != 8:
            raise ValueError('Informe um CEP com 8 dígitos.')


def garantir_endereco_cliente(cep):
    """Cria um endereco pendente quando o CEP ainda nao existe."""
    execute_query(
        'INSERT INTO `endereço` (cep, logradouro, cidade, uf) VALUES (%s, NULL, %s, %s) '
        'ON DUPLICATE KEY UPDATE cep=VALUES(cep)',
        (cep, 'PENDENTE', '--'),
    )


def criar_login_cliente(cnpj, razao_social, email):
    """Cria o acesso local inicial para um novo cliente cadastrado pelo admin."""
    senha_inicial = 'Cliente@123'
    with get_connection() as conexao:
        existente = conexao.execute(
            "SELECT id FROM usuarios WHERE documento = ? AND tipo = 'cliente'",
            (cnpj,),
        ).fetchone()
        if existente:
            conexao.execute(
                'UPDATE usuarios SET nome = ?, email = ?, ativo = 1 WHERE id = ?',
                (razao_social, email or None, existente['id']),
            )
            conexao.commit()
            return False
        conexao.execute(
            'INSERT INTO usuarios (nome, email, documento, senha, tipo, ativo) '
            "VALUES (?, ?, ?, ?, 'cliente', 1)",
            (razao_social, email or None, cnpj, generate_password_hash(senha_inicial)),
        )
        conexao.commit()
    return True


@app.route('/')
def home():
    """Renderiza a pagina inicial publica."""
    return render_template('index.html')


@app.route('/sobre')
def sobre():
    """Renderiza a pagina institucional sobre o posto."""
    return render_template('sobre.html')


@app.route('/servicos')
def servicos():
    """Mostra a pagina geral de servicos com precos vindos do banco."""
    return render_template('servicos.html', precos=carregar_precos_base())


@app.route('/servicos/combustivel')
def servico_combustivel():
    """Mostra a pagina detalhada dos combustiveis."""
    return render_template('servicos/combustivel.html', itens=SERVICOS_DETALHADOS['combustivel'])


@app.route('/servicos/lavagem')
def servico_lavagem():
    """Mostra a pagina detalhada dos servicos de lavagem."""
    return render_template('servicos/lavagem.html', itens=SERVICOS_DETALHADOS['lavagem'])


@app.route('/servicos/estacionamento')
def servico_estacionamento():
    """Mostra a pagina detalhada de estacionamento."""
    return render_template('servicos/estacionamento.html', itens=SERVICOS_DETALHADOS['estacionamento'])


@app.route('/esg')
def esg():
    """Renderiza a pagina ESG/sustentabilidade."""
    return render_template('esg.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Autentica admin, funcionario ou cliente e grava os dados na sessao."""
    tipo = request.args.get('tipo', 'cliente')
    erro = None

    if request.method == 'POST':
        # O mesmo formulario atende perfis internos e clientes.
        tipo = request.form.get('tipo', 'cliente')
        identificador = request.form.get('cnpj', '').strip()
        senha = request.form.get('senha', '')
        logger_acesso.info(f'Tentativa de login - perfil={tipo}, ip={request.remote_addr}')

        if tipo in ['admin', 'funcionario']:
            # Admin e funcionario usam o banco local de usuarios.
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
            # Cliente entra com CNPJ e tambem precisa existir no MySQL.
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
                erro = 'CNPJ ou senha incorretos para a Área do Cliente.'

    return render_template('login.html', tipo=tipo, erro=erro)


@app.route('/redefinir-senha', methods=['GET', 'POST'])
def redefinir_senha():
    """Fluxo demonstrativo de validacao para redefinicao de senha."""
    enviado = False
    erro = ''
    cnpj = ''
    email = ''
    email_mascarado = ''
    etapa = request.form.get('etapa', 'cnpj')

    if request.method == 'POST':
        # Primeiro confirma se o CNPJ existe; depois valida o e-mail cadastrado.
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
    """Limpa a sessao e leva o usuario de volta para a pagina inicial."""
    session.clear()
    return redirect(url_for('home'))


@app.route('/contato', methods=['GET', 'POST'])
def contato():
    """Recebe mensagens do formulario de contato e tenta notificar por e-mail."""
    enviado = False
    erro_envio = ''
    aviso_envio = ''

    if request.method == 'POST':
        # Normaliza os dados antes de salvar e montar o corpo do e-mail.
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
    """Painel administrativo para clientes, servicos, boletos e relatorios."""
    mensagem = ''
    erro = ''
    painel_ativo = request.args.get('painel', 'dashboard')

    if request.method == 'POST':
        # O campo acao define qual operacao administrativa sera executada.
        acoes = request.form.getlist('acao')
        acao = acoes[-1] if acoes else ''
        painel_ativo = request.form.get('painel', painel_ativo)
        try:
            if acao == 'salvar_servico':
                # Cria um novo servico ou atualiza um servico existente.
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
                    mensagem = 'Serviço atualizado com sucesso.'
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
                    mensagem = 'Serviço adicionado com sucesso.'
                    logger_auditoria.info(f'Admin criou servico id={proximo} nome={nome}')

            elif acao == 'excluir_servico':
                # Remove um servico cadastrado, se nao houver bloqueio relacional.
                servico_id = request.form.get('servico_id')
                execute_query('DELETE FROM `serviço_utilizado` WHERE `id_Serviço_utilizado`=%s', (servico_id,))
                mensagem = 'Serviço excluído com sucesso.'
                logger_auditoria.info(f'Admin excluiu servico id={servico_id}')

            elif acao == 'salvar_cliente':
                # Cria ou atualiza cliente e sincroniza seus veiculos.
                cnpj = somente_digitos(request.form.get('cnpj'))
                cnpj_original = somente_digitos(request.form.get('cnpj_original'))
                dados = (
                    request.form.get('razao_social', '').strip(),
                    somente_digitos(request.form.get('telefone')),
                    request.form.get('email', '').strip(),
                )
                veiculos = parse_veiculos_request(request.form)
                if cnpj_original:
                    validar_dados_cliente(cnpj_original, dados, veiculos)
                    placa_principal = salvar_veiculos_cliente(cnpj_original, veiculos) if veiculos else None
                    campos = 'razao_social=%s, telefone=%s, email=%s'
                    valores = [*dados]
                    valores.append(cnpj_original)
                    execute_query(
                        f'UPDATE cliente SET {campos} WHERE cnpj=%s',
                        tuple(valores),
                    )
                    mensagem = 'Cliente atualizado com sucesso.'
                    logger_auditoria.info(f'Admin editou cliente {mascarar_cnpj(cnpj_original)}')
                else:
                    cep = somente_digitos(request.form.get('cep'))
                    validar_dados_cliente(cnpj, dados, veiculos, cep)
                    garantir_endereco_cliente(cep)
                    execute_query(
                        'INSERT INTO cliente '
                        '(cnpj, razao_social, telefone, email, complemento, numero, `Endereço_cep`) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                        (
                            cnpj,
                            dados[0],
                            dados[1],
                            dados[2],
                            request.form.get('complemento', '').strip() or None,
                            request.form.get('numero') or None,
                            cep,
                        ),
                    )
                    salvar_veiculos_cliente(cnpj, veiculos)
                    login_criado = criar_login_cliente(cnpj, dados[0], dados[2])
                    mensagem = 'Cliente adicionado com sucesso.'
                    if login_criado:
                        mensagem += f' Login inicial: {cnpj} | Senha: Cliente@123'
                    logger_auditoria.info(f'Admin criou cliente {mascarar_cnpj(cnpj)}')

            elif acao == 'excluir_cliente':
                # Exclui o cliente pelo CNPJ informado no formulario.
                cnpj = somente_digitos(request.form.get('cnpj'))
                execute_query('DELETE FROM cliente WHERE cnpj=%s', (cnpj,))
                mensagem = 'Cliente excluído com sucesso.'
                logger_auditoria.info(f'Admin excluiu cliente {mascarar_cnpj(cnpj)}')

            elif acao == 'salvar_boleto':
                # Atualiza um boleto gerado automaticamente com sua fatura.
                boleto_id = request.form.get('boleto_id')
                vencimento = request.form.get('data_vencimento')
                emissao = request.form.get('data_emissao')
                codigo = request.form.get('codigo_barras', '').strip()
                status = request.form.get('status_pagamento', '').strip().upper()
                if boleto_id:
                    execute_query(
                        'UPDATE boleto SET data_vencimento=%s, data_emissao=%s, codigo_barras=%s, '
                        'status_pagamento=%s WHERE id_Boleto=%s',
                        (vencimento, emissao, codigo, status, boleto_id),
                    )
                    mensagem = 'Boleto atualizado com sucesso.'
                    logger_auditoria.info(f'Admin editou boleto id={boleto_id}')
                else:
                    erro = 'Selecione um boleto existente para editar.'

            elif acao == 'excluir_boleto':
                # Remove um boleto especifico.
                boleto_id = request.form.get('boleto_id')
                execute_query('DELETE FROM boleto WHERE id_Boleto=%s', (boleto_id,))
                mensagem = 'Boleto excluído com sucesso.'
                logger_auditoria.info(f'Admin excluiu boleto id={boleto_id}')

        except ValueError as exc:
            erro = str(exc)
        except Exception as exc:
            erro = 'Não foi possível concluir a operação. Verifique se há registros vinculados.'
            logger_erro.exception(f'Erro admin: {exc}')

    # Filtros usados para manter as buscas do dashboard administrativo.
    cliente_busca = request.args.get('cliente_busca', '').strip()
    boleto_busca = request.args.get('boleto_busca', '').strip()
    servico_busca = request.args.get('servico_busca', '').strip()
    acesso_busca = request.args.get('acesso_busca', '').strip()
    faturamento_busca = request.args.get('faturamento_busca', '').strip()
    competencia = request.args.get('competencia', '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}', competencia or ''):
        competencia = ''

    # Indicadores principais exibidos no topo do painel.
    clientes_total = fetch_one('SELECT COUNT(*) AS total FROM cliente')['total']
    resumo = porcentagem_status(resumo_boletos())
    resumo['clientes'] = clientes_total
    resumo['faturamento'] = faturamento_estimado()
    resumo['servicos'] = servicos_mais_utilizados()

    # Listagem de clientes, incluindo uma placa principal e a lista completa de veiculos.
    clientes_where = ''
    clientes_params = ()
    if cliente_busca:
        clientes_where = 'WHERE c.cnpj LIKE %s OR c.razao_social LIKE %s OR c.email LIKE %s'
        clientes_params = (f'%{cliente_busca}%', f'%{cliente_busca}%', f'%{cliente_busca}%')

    clientes = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, c.complemento, c.numero, c.`Endereço_cep` AS cep, '
        'principal.placa_veiculo AS placa, principal.modelo AS veiculo_modelo, principal.Ano_veiculo AS veiculo_ano, '
        '(SELECT GROUP_CONCAT(DISTINCT CONCAT(vv.placa_veiculo, '
        "CASE WHEN vv.modelo IS NOT NULL THEN CONCAT(' - ', vv.modelo) ELSE '' END, "
        "CASE WHEN vv.Ano_veiculo IS NOT NULL THEN CONCAT(' - ', vv.Ano_veiculo) ELSE '' END) SEPARATOR ', ') "
        'FROM veiculo vv '
        'WHERE vv.cliente_cnpj = c.cnpj) AS veiculos '
        'FROM cliente c '
        'LEFT JOIN veiculo principal ON principal.placa_veiculo = ('
        'SELECT v2.placa_veiculo FROM veiculo v2 WHERE v2.cliente_cnpj = c.cnpj ORDER BY v2.placa_veiculo LIMIT 1'
        ') '
        f'{clientes_where} ORDER BY c.razao_social LIMIT 30',
        clientes_params,
    )
    veiculos_por_cliente = {}
    if clientes:
        placeholders = ', '.join(['%s'] * len(clientes))
        linhas_veiculos = fetch_all(
            'SELECT v.cliente_cnpj AS cnpj, v.placa_veiculo AS placa, '
            'v.modelo, v.Ano_veiculo AS ano '
            'FROM veiculo v '
            f'WHERE v.cliente_cnpj IN ({placeholders}) '
            'ORDER BY v.cliente_cnpj, v.placa_veiculo',
            tuple(cliente['cnpj'] for cliente in clientes),
        )
        for veiculo in linhas_veiculos:
            veiculos_por_cliente.setdefault(veiculo['cnpj'], []).append(veiculo)
    for cliente in clientes:
        cliente['veiculos_lista'] = veiculos_por_cliente.get(cliente['cnpj'], [])
    enderecos = fetch_all(
        'SELECT cep, logradouro, cidade, uf FROM `endereço` ORDER BY cidade, logradouro, cep'
    )

    # Listagem de boletos e faturas disponiveis para operacoes manuais.
    boletos_where = ''
    boletos_params = ()
    if boleto_busca:
        boletos_where = (
            'WHERE c.razao_social LIKE %s OR c.cnpj LIKE %s OR su.nome LIKE %s OR b.status_pagamento LIKE %s'
        )
        boletos_params = (f'%{boleto_busca}%', f'%{boleto_busca}%', f'%{boleto_busca}%', f'%{boleto_busca}%')
    boletos = listar_boletos(boletos_where, boletos_params, limite=30)
    resumos_mensais = listar_resumos_mensais(faturamento_busca, competencia)
    for resumo_mensal in resumos_mensais:
        resumo_mensal['itens'] = listar_itens_resumo_mensal(
            resumo_mensal['cnpj'],
            resumo_mensal['competencia'],
        )

    # Filtro local dos servicos cadastrados por nome ou descricao.
    precos = carregar_precos_base()
    if servico_busca:
        termo = servico_busca.lower()
        precos = [
            servico for servico in precos
            if termo in str(servico.get('nome') or '').lower()
            or termo in str(servico.get('descricao') or '').lower()
        ]

    # Ultimos acessos lidos do arquivo de log.
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
        enderecos=enderecos,
        boletos=boletos,
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
        painel_ativo=painel_ativo,
        mensagem=mensagem,
        erro=erro,
    )


@app.route('/funcionario/dashboard', methods=['GET', 'POST'])
@login_obrigatorio('funcionario')
def dashboard_funcionario():
    """Painel operacional para consulta de clientes e registro de servicos."""
    mensagem = ''
    erro = ''
    garantir_coluna_data_servico()

    if request.method == 'POST':
        # Registro de servico: cliente + veiculo + tipo + quantidade + data.
        cnpj = somente_digitos(request.form.get('cnpj'))
        placa_veiculo = ''.join(
            caractere for caractere in (request.form.get('placa_veiculo') or '').upper()
            if caractere.isalnum()
        )[:7]
        servico_id = request.form.get('tipo_servico')
        quantidade = Decimal(request.form.get('quantidade', '1').replace(',', '.'))
        data_registro = request.form.get('data_registro') or date.today().isoformat()
        try:
            # Confere se a placa realmente pertence ao CNPJ informado.
            cliente = fetch_one(
                'SELECT base.cnpj, base.razao_social, v.placa_veiculo AS Veiculo_placa_veiculo '
                'FROM cliente base '
                'JOIN veiculo v ON v.cliente_cnpj = base.cnpj '
                'WHERE base.cnpj = %s AND v.placa_veiculo = %s '
                'LIMIT 1',
                (cnpj, placa_veiculo),
            )
            if not cliente:
                erro = 'Cliente ou veículo não encontrado para registrar o serviço.'
            elif not placa_veiculo:
                erro = 'Selecione um veículo cadastrado para este cliente.'
            elif (bloqueio := cliente_bloqueado_por_inadimplencia(cnpj)):
                vencimento = bloqueio.get('data_vencimento')
                vencimento_texto = vencimento.strftime('%d/%m/%Y') if hasattr(vencimento, 'strftime') else str(vencimento)
                erro = (
                    'Cliente bloqueado por inadimplência. '
                    f'Existe boleto não pago vencido em {vencimento_texto}, há mais de 2 meses.'
                )
                logger_auditoria.info(
                    f'Registro de servico bloqueado por inadimplencia cliente={mascarar_cnpj(cnpj)} '
                    f'boleto={bloqueio.get("id_Boleto")}'
                )
            else:
                # Cada servico registrado gera uma fatura e um boleto demonstrativo.
                servico_registrado_id = execute_insert_id(
                    'INSERT INTO `serviço` '
                    '(qunt_utilizada, serviço_utilizado_id_Serviço_utilizado, Veiculo_placa_veiculo, data_registro) '
                    'VALUES (%s, %s, %s, %s)',
                    (quantidade, servico_id, cliente['Veiculo_placa_veiculo'], data_registro),
                )
                proxima_fatura = fetch_one('SELECT COALESCE(MAX(id_Fatura), 0) + 1 AS id FROM fatura')['id']
                execute_query(
                    'INSERT INTO fatura (id_Fatura, serviço_id_Serviço, cliente_cnpj) VALUES (%s, %s, %s)',
                    (proxima_fatura, servico_registrado_id, cnpj),
                )
                criar_boleto_para_fatura(proxima_fatura)
                mensagem = (
                    f'Serviço registrado para {cliente["razao_social"]} '
                    f'no veículo {cliente["Veiculo_placa_veiculo"]}.'
                )
                logger_auditoria.info(
                    f'Funcionario registrou servico para {mascarar_cnpj(cnpj)} '
                    f'veiculo={cliente["Veiculo_placa_veiculo"]} data={data_registro}'
                )
        except Exception as exc:
            erro = 'Não foi possível registrar o serviço.'
            logger_erro.exception(f'Erro funcionario: {exc}')

    # Filtros que controlam as abas e consultas do painel do funcionario.
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

    # Lista resumida dos clientes para consulta operacional.
    clientes = fetch_all(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, '
        'principal.placa_veiculo AS placa, principal.modelo AS veiculo_modelo, principal.Ano_veiculo AS veiculo_ano, '
        'COUNT(DISTINCT b.id_Boleto) AS total_boletos, '
        "SUM(CASE WHEN UPPER(b.status_pagamento) = 'EM ABERTO' THEN 1 ELSE 0 END) AS boletos_abertos "
        'FROM cliente c '
        'LEFT JOIN veiculo principal ON principal.placa_veiculo = ('
        'SELECT v2.placa_veiculo FROM veiculo v2 WHERE v2.cliente_cnpj = c.cnpj ORDER BY v2.placa_veiculo LIMIT 1'
        ') '
        'LEFT JOIN fatura f ON f.cliente_cnpj = c.cnpj '
        'LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura '
        f'{where} '
        'GROUP BY c.cnpj, c.razao_social, c.telefone, c.email, principal.placa_veiculo, principal.modelo, principal.Ano_veiculo '
        'ORDER BY c.razao_social',
        params,
    )
    for cliente in clientes:
        cliente['cnpj_mascarado'] = mascarar_cnpj(cliente['cnpj'])

    # Dados usados pelo formulario de registro de servico.
    clientes_registro = fetch_all(
        'SELECT c.cnpj, c.razao_social '
        'FROM cliente c '
        'ORDER BY c.razao_social'
    )
    todos_veiculos_cliente = fetch_all(
        'SELECT c.cnpj, c.razao_social, v.placa_veiculo AS placa, '
        'v.modelo AS veiculo_modelo, v.Ano_veiculo AS veiculo_ano '
        'FROM cliente c '
        'JOIN veiculo v ON v.cliente_cnpj = c.cnpj '
        'ORDER BY c.razao_social, v.placa_veiculo'
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

    # Filtros de boletos combinam busca textual e status.
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
    # Decide qual aba fica ativa depois de buscas ou postagens.
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


@app.route('/cliente/dashboard', methods=['GET', 'POST'])
@login_obrigatorio('cliente')
def dashboard_cliente():
    """Area do cliente com boletos, servicos utilizados e indicadores."""
    cnpj = session.get('usuario_identificador')
    mensagem = ''
    erro = ''
    endereco_cliente = fetch_one(
        'SELECT c.cnpj, c.razao_social, c.telefone, c.email, '
        'c.`Endereço_cep` AS cep, c.numero, c.complemento, '
        'e.logradouro, e.cidade, e.uf '
        'FROM cliente c JOIN `endereço` e ON e.cep = c.`Endereço_cep` '
        'WHERE c.cnpj = %s',
        (cnpj,),
    )
    if request.method == 'POST' and request.form.get('acao') == 'completar_endereco':
        logradouro = request.form.get('logradouro', '').strip()
        cidade = request.form.get('cidade', '').strip()
        uf = request.form.get('uf', '').strip().upper()
        numero = request.form.get('numero') or None
        complemento = request.form.get('complemento', '').strip() or None
        if not logradouro or not cidade or len(uf) != 2:
            erro = 'Informe logradouro, cidade e UF com 2 letras.'
        elif len(logradouro) > 48 or len(cidade) > 48:
            erro = 'Logradouro e cidade devem ter no máximo 48 caracteres.'
        else:
            execute_query(
                'UPDATE `endereço` e JOIN cliente c ON c.`Endereço_cep` = e.cep '
                'SET e.logradouro=%s, e.cidade=%s, e.uf=%s '
                'WHERE c.cnpj=%s',
                (logradouro, cidade, uf, cnpj),
            )
            execute_query(
                'UPDATE cliente SET numero=%s, complemento=%s WHERE cnpj=%s',
                (numero, complemento, cnpj),
            )
            endereco_cliente = fetch_one(
                'SELECT c.cnpj, c.razao_social, c.telefone, c.email, '
                'c.`Endereço_cep` AS cep, c.numero, c.complemento, '
                'e.logradouro, e.cidade, e.uf '
                'FROM cliente c JOIN `endereço` e ON e.cep = c.`Endereço_cep` '
                'WHERE c.cnpj = %s',
                (cnpj,),
            )
            mensagem = 'Endereço atualizado com sucesso.'
            logger_auditoria.info(f'Cliente completou endereco {mascarar_cnpj(cnpj)}')
    endereco_pendente = bool(
        endereco_cliente
        and (
            not endereco_cliente.get('logradouro')
            or endereco_cliente.get('cidade') == 'PENDENTE'
            or endereco_cliente.get('uf') == '--'
        )
    )
    veiculos_cliente = fetch_all(
        'SELECT placa_veiculo, modelo, Ano_veiculo AS ano '
        'FROM veiculo WHERE cliente_cnpj = %s ORDER BY placa_veiculo',
        (cnpj,),
    )
    periodo_chave = request.args.get('periodo', '90')
    if periodo_chave not in PERIODOS_CLIENTE:
        periodo_chave = '90'
    periodo = PERIODOS_CLIENTE[periodo_chave]

    # Monta filtros de periodo para boletos e servicos do cliente logado.
    where_boletos = 'WHERE c.cnpj = %s'
    where_servicos = 'WHERE c.cnpj = %s'
    if periodo['dias']:
        where_boletos += f' AND b.data_vencimento >= DATE_SUB(CURDATE(), INTERVAL {periodo["dias"]} DAY)'
        where_servicos += f' AND (b.data_vencimento IS NULL OR b.data_vencimento >= DATE_SUB(CURDATE(), INTERVAL {periodo["dias"]} DAY))'

    # Busca boletos, encontra um boleto em aberto e calcula o resumo financeiro.
    boletos = listar_boletos(where_boletos, (cnpj,), limite=30)
    boleto_aberto = next((b for b in boletos if str(b['status_pagamento']).upper() == 'EM ABERTO'), None)
    servicos_cliente = fetch_all(
        'SELECT DISTINCT s.id_Serviço AS servico_id, su.nome, su.descrição AS descricao, '
        'su.valor_unitario, su.desconto, s.qunt_utilizada, s.data_registro '
        'FROM fatura f '
        'JOIN cliente c ON c.cnpj = f.cliente_cnpj '
        'JOIN `serviço` s ON s.id_Serviço = f.serviço_id_Serviço '
        'JOIN `serviço_utilizado` su ON su.id_Serviço_utilizado = s.serviço_utilizado_id_Serviço_utilizado '
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
        cadastro=endereco_cliente,
        veiculos=veiculos_cliente,
        endereco=endereco_cliente,
        endereco_pendente=endereco_pendente,
        mensagem=mensagem,
        erro=erro,
    )


@app.errorhandler(404)
def not_found(_):
    """Pagina amigavel quando a rota nao existe."""
    return render_template('erro.html', erro='Página não encontrada'), 404


@app.errorhandler(500)
def internal_error(_):
    """Pagina amigavel para erros internos, registrando o problema no log."""
    logger_erro.exception('Erro interno do servidor')
    return render_template('erro.html', erro='Erro interno do servidor'), 500


if __name__ == '__main__':
    # Permite executar localmente com: python app.py
    app.run(
        debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', '8001')),
    )

