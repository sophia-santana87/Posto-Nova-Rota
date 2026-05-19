from pathlib import Path
from datetime import datetime
from functools import wraps
from uuid import uuid4
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, session
from database.conexao import init_db, salvar_mensagem_contato
from database.mysql_conexao import fetch_all, fetch_one

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

app = Flask(__name__)
app.secret_key = 'nova-rota-dev-secret'
init_db()


CREDENCIAIS_INTERNAS = {
    'admin': {
        'identificador': 'admin',
        'senha': 'admin123',
        'nome': 'Administrador',
    },
    'funcionario': {
        'identificador': 'funcionario',
        'senha': 'func123',
        'nome': 'João Silva',
    },
}

SESSOES_ATIVAS_RESTRITAS = {}
LIMITES_SESSAO_POR_PERFIL = {
    'admin': 1,
    'funcionario': 10,
}


def login_required(*perfis):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            usuario = session.get('usuario')
            if not usuario:
                return redirect(url_for('login'))

            if usuario.get('tipo') in LIMITES_SESSAO_POR_PERFIL:
                chave = chave_sessao_restrita(usuario)
                tokens_ativos = SESSOES_ATIVAS_RESTRITAS.get(chave, set())
                if session.get('session_token') not in tokens_ativos:
                    session.clear()
                    return redirect(url_for('login', tipo=usuario.get('tipo'), motivo='sessao_expirada'))

            if perfis and usuario.get('tipo') not in perfis:
                return redirect(url_for('login', tipo=usuario.get('tipo', 'cliente')))

            return func(*args, **kwargs)

        return wrapper

    return decorator


def chave_sessao_restrita(usuario):
    return f"{usuario.get('tipo')}:{usuario.get('identificador')}"


def registrar_sessao(usuario):
    token = uuid4().hex
    session['usuario'] = usuario
    session['session_token'] = token

    if usuario.get('tipo') in LIMITES_SESSAO_POR_PERFIL:
        chave = chave_sessao_restrita(usuario)
        SESSOES_ATIVAS_RESTRITAS.setdefault(chave, set()).add(token)


def encerrar_sessao_atual():
    usuario = session.get('usuario')
    token = session.get('session_token')

    if usuario and usuario.get('tipo') in LIMITES_SESSAO_POR_PERFIL:
        chave = chave_sessao_restrita(usuario)
        tokens_ativos = SESSOES_ATIVAS_RESTRITAS.get(chave, set())
        tokens_ativos.discard(token)
        if tokens_ativos:
            SESSOES_ATIVAS_RESTRITAS[chave] = tokens_ativos
        else:
            SESSOES_ATIVAS_RESTRITAS.pop(chave, None)

    session.clear()


def sessao_restrita_em_uso(usuario):
    limite = LIMITES_SESSAO_POR_PERFIL.get(usuario.get('tipo'))
    if not limite:
        return False

    chave = chave_sessao_restrita(usuario)
    return len(SESSOES_ATIVAS_RESTRITAS.get(chave, set())) >= limite


def limpar_documento(valor):
    return ''.join(char for char in (valor or '') if char.isdigit())


def autenticar_usuario(tipo, identificador, senha):
    identificador_limpo = limpar_documento(identificador)

    if tipo in CREDENCIAIS_INTERNAS:
        credencial = CREDENCIAIS_INTERNAS[tipo]
        if identificador.strip().lower() == credencial['identificador'] and senha == credencial['senha']:
            return {
                'tipo': tipo,
                'nome': credencial['nome'],
                'identificador': credencial['identificador'],
            }
        return None

    if tipo == 'cliente' and senha == 'cliente123':
        cliente = fetch_one(
            """
            SELECT cnpj, razao_social, email
            FROM cliente
            WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = %s
               OR cnpj = %s
            LIMIT 1
            """,
            (identificador_limpo, identificador_limpo),
        )
        if cliente:
            return {
                'tipo': 'cliente',
                'nome': cliente['razao_social'],
                'identificador': cliente['cnpj'],
                'email': cliente.get('email'),
            }

    return None


def resumo_admin():
    clientes = fetch_one('SELECT COUNT(*) AS total FROM cliente')['total']
    boletos_pagos = fetch_one("SELECT COUNT(*) AS total FROM boleto WHERE status_pagamento = 'PAGO'")['total']
    boletos_atrasados = fetch_one("SELECT COUNT(*) AS total FROM boleto WHERE status_pagamento = 'ATRASADO'")['total']
    faturamento = fetch_one(
        """
        SELECT COALESCE(SUM(s.qunt_utilizada * (su.valor_unitario - COALESCE(su.desconto, 0))), 0) AS total
        FROM `serviço` s
        JOIN `serviço_utilizado` su
          ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        """
    )['total']
    servicos = fetch_all(
        """
        SELECT su.nome, COUNT(*) AS total
        FROM `serviço` s
        JOIN `serviço_utilizado` su
          ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        GROUP BY su.nome
        ORDER BY total DESC
        """
    )
    total_servicos = sum(item['total'] for item in servicos) or 1

    return {
        'clientes': clientes,
        'boletos_pagos': boletos_pagos,
        'boletos_atrasados': boletos_atrasados,
        'faturamento': float(faturamento),
        'servicos': [
            {
                'nome': item['nome'],
                'percentual': round((item['total'] / total_servicos) * 100),
            }
            for item in servicos
        ],
    }


def boletos_cliente(cnpj):
    return fetch_all(
        """
        SELECT
            b.data_vencimento,
            su.nome AS servico,
            (s.qunt_utilizada * (su.valor_unitario - COALESCE(su.desconto, 0))) AS valor,
            b.status_pagamento
        FROM cliente c
        JOIN fatura f ON f.id_Fatura = c.Fatura_id_Fatura
        JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura
        JOIN `serviço` s ON s.`id_Serviço` = f.`Serviço_id_Serviço`
        JOIN `serviço_utilizado` su ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        WHERE c.cnpj = %s
        ORDER BY b.data_vencimento DESC
        """,
        (cnpj,),
    )


def servicos_recentes():
    return fetch_all(
        """
        SELECT c.razao_social, su.nome AS servico,
               (s.qunt_utilizada * (su.valor_unitario - COALESCE(su.desconto, 0))) AS valor
        FROM cliente c
        JOIN fatura f ON f.id_Fatura = c.Fatura_id_Fatura
        JOIN `serviço` s ON s.`id_Serviço` = f.`Serviço_id_Serviço`
        JOIN `serviço_utilizado` su ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        ORDER BY f.id_Fatura DESC
        LIMIT 8
        """
    )


def resumo_funcionario():
    status = fetch_all(
        """
        SELECT status_pagamento, COUNT(*) AS total
        FROM boleto
        GROUP BY status_pagamento
        """
    )
    contagem = {item['status_pagamento']: item['total'] for item in status}
    total_boletos = sum(contagem.values()) or 0
    total_clientes = fetch_one('SELECT COUNT(*) AS total FROM cliente')['total']
    valor_em_aberto = fetch_one(
        """
        SELECT COALESCE(SUM(s.qunt_utilizada * (su.valor_unitario - COALESCE(su.desconto, 0))), 0) AS total
        FROM boleto b
        JOIN fatura f ON f.id_Fatura = b.Fatura_id_Fatura
        JOIN `serviço` s ON s.`id_Serviço` = f.`Serviço_id_Serviço`
        JOIN `serviço_utilizado` su ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        WHERE b.status_pagamento = 'EM ABERTO'
        """
    )['total']
    proximos_boletos = fetch_all(
        """
        SELECT c.razao_social, b.data_vencimento, b.status_pagamento,
               su.nome AS servico,
               (s.qunt_utilizada * (su.valor_unitario - COALESCE(su.desconto, 0))) AS valor
        FROM cliente c
        JOIN fatura f ON f.id_Fatura = c.Fatura_id_Fatura
        JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura
        JOIN `serviço` s ON s.`id_Serviço` = f.`Serviço_id_Serviço`
        JOIN `serviço_utilizado` su ON su.`id_Serviço_utilizado` = s.`Serviço_utilizado_id_Serviço_utilizado`
        WHERE b.status_pagamento IN ('EM ABERTO', 'ATRASADO')
        ORDER BY b.data_vencimento ASC
        LIMIT 6
        """
    )
    servicos = servicos_recentes()
    total_servicos = sum(float(item['valor'] or 0) for item in servicos) or 1

    return {
        'clientes': total_clientes,
        'total_boletos': total_boletos,
        'boletos_pagos': contagem.get('PAGO', 0),
        'boletos_abertos': contagem.get('EM ABERTO', 0),
        'boletos_atrasados': contagem.get('ATRASADO', 0),
        'valor_em_aberto': float(valor_em_aberto or 0),
        'proximos_boletos': proximos_boletos,
        'servicos': [
            {
                'nome': item['servico'],
                'cliente': item['razao_social'],
                'valor': float(item['valor'] or 0),
                'percentual': round((float(item['valor'] or 0) / total_servicos) * 100),
            }
            for item in servicos[:5]
        ],
    }


def clientes_funcionario(termo=''):
    filtro = f"%{termo}%"
    return fetch_all(
        """
        SELECT c.razao_social, c.email,
               COUNT(b.Fatura_id_Fatura) AS boletos,
               SUM(CASE WHEN b.status_pagamento = 'EM ABERTO' THEN 1 ELSE 0 END) AS abertos,
               SUM(CASE WHEN b.status_pagamento = 'ATRASADO' THEN 1 ELSE 0 END) AS atrasados,
               MAX(b.data_vencimento) AS ultimo_vencimento
        FROM cliente c
        LEFT JOIN fatura f ON f.id_Fatura = c.Fatura_id_Fatura
        LEFT JOIN boleto b ON b.Fatura_id_Fatura = f.id_Fatura
        WHERE %s = '' OR c.razao_social LIKE %s
        GROUP BY c.razao_social, c.email
        ORDER BY c.razao_social
        LIMIT 8
        """,
        (termo, filtro),
    )

@app.context_processor
def inject_inline_css():
    css_path = Path(app.root_path) / 'static' / 'css' / 'style.css'
    try:
        return {'inline_css': css_path.read_text(encoding='utf-8')}
    except OSError:
        return {'inline_css': ''}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/sobre')
def sobre():
    return render_template('sobre.html')

@app.route('/servicos')
def servicos():
    return render_template('servicos.html')

@app.route('/servicos/combustivel')
def servico_combustivel():
    return render_template('servicos/combustivel.html')

@app.route('/servicos/lavagem')
def servico_lavagem():
    return render_template('servicos/lavagem.html')

@app.route('/servicos/estacionamento')
def servico_estacionamento():
    return render_template('servicos/estacionamento.html')

@app.route('/esg')
def esg():
    return render_template('esg.html')

def salvar_contato(dados):
    salvar_mensagem_contato(dados)

    logs_dir = Path(app.root_path) / 'logs'
    logs_dir.mkdir(exist_ok=True)
    arquivo = logs_dir / 'contatos.log'
    data_envio = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    with arquivo.open('a', encoding='utf-8') as log:
        log.write(
            f"[{data_envio}] Nova mensagem de contato\n"
            f"Nome: {dados.get('nome')}\n"
            f"E-mail: {dados.get('email')}\n"
            f"Telefone: {dados.get('telefone') or 'Não informado'}\n"
            f"Assunto: {dados.get('assunto')}\n"
            f"Mensagem: {dados.get('mensagem')}\n"
            f"{'-' * 60}\n"
        )


def enviar_email_contato(dados):
    smtp_host = os.environ.get('MAIL_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('MAIL_PORT', '587'))
    smtp_user = os.environ.get('MAIL_USER')
    smtp_password = os.environ.get('MAIL_PASSWORD')
    sender = os.environ.get('MAIL_SENDER', smtp_user or 'no-reply@novarota.com')
    recipient = os.environ.get('MAIL_RECIPIENT')

    if not smtp_user or not smtp_password or not recipient:
        raise RuntimeError(
            'E-mail não configurado: defina MAIL_USER, MAIL_PASSWORD e MAIL_RECIPIENT no ambiente.'
        )

    mensagem = EmailMessage()
    mensagem['Subject'] = f"Novo contato - {dados.get('assunto', 'Sem assunto')}"
    mensagem['From'] = sender
    mensagem['To'] = recipient
    mensagem.set_content(
        f"Nova mensagem de contato enviada pelo site.\n\n"
        f"Nome: {dados.get('nome')}\n"
        f"E-mail: {dados.get('email')}\n"
        f"Telefone: {dados.get('telefone') or 'Não informado'}\n"
        f"Assunto: {dados.get('assunto')}\n"
        f"Mensagem:\n{dados.get('mensagem')}\n"
    )

    with smtplib.SMTP(smtp_host, smtp_port) as servidor:
        servidor.starttls()
        servidor.login(smtp_user, smtp_password)
        servidor.send_message(mensagem)


@app.route('/contato', methods=['GET', 'POST'])
def contato():
    enviado = False
    erro_envio = ''
    aviso_envio = ''
    contato_enviado = {}

    if request.method == 'POST':
        contato_enviado = {
            'nome': request.form.get('nome', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telefone': request.form.get('telefone', '').strip(),
            'assunto': request.form.get('assunto', '').strip(),
            'mensagem': request.form.get('mensagem', '').strip(),
        }
        dados_contato = contato_enviado.copy()
        try:
            salvar_contato(dados_contato)
        except Exception as erro:
            erro_envio = f'Não foi possível salvar sua mensagem: {erro}'
        else:
            enviado = True
            contato_enviado = {}

        if enviado:
            try:
                enviar_email_contato(dados_contato)
            except Exception as erro:
                aviso_envio = f'Sua mensagem foi registrada, mas o e-mail automático não foi enviado: {erro}'

    return render_template(
        'contato.html',
        enviado=enviado,
        erro_envio=erro_envio,
        aviso_envio=aviso_envio,
        contato_enviado=contato_enviado
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    tipo = request.args.get('tipo', 'cliente')
    erro = ''
    if request.args.get('motivo') == 'sessao_expirada':
        erro = 'Sua sessão foi encerrada porque outro acesso foi iniciado para este usuário.'

    if request.method == 'POST':
        tipo = request.form.get('tipo', 'cliente')
        identificador = request.form.get('cnpj', '').strip()
        senha = request.form.get('senha', '')
        usuario = autenticar_usuario(tipo, identificador, senha)

        if not usuario:
            return render_template('login.html', tipo=tipo, erro='Dados de acesso inválidos.')

        if sessao_restrita_em_uso(usuario):
            return render_template(
                'login.html',
                tipo=tipo,
                erro='O limite de sessões simultâneas para este perfil foi atingido. Encerre uma sessão ativa antes de entrar novamente.'
            )

        registrar_sessao(usuario)
        destinos = {
            'cliente': 'dashboard_cliente',
            'funcionario': 'dashboard_funcionario',
            'admin': 'dashboard_admin',
        }
        return redirect(url_for(destinos.get(tipo, 'dashboard_cliente')))

    return render_template('login.html', tipo=tipo, erro=erro)


@app.route('/logout')
def logout():
    encerrar_sessao_atual()
    return redirect(url_for('home'))

@app.route('/cliente')
@login_required('cliente')
def dashboard_cliente():
    usuario = session['usuario']
    boletos = boletos_cliente(usuario['identificador'])
    aberto = next((boleto for boleto in boletos if boleto['status_pagamento'] == 'EM ABERTO'), None)
    return render_template(
        'cliente/dashboard_cliente.html',
        usuario=usuario,
        boletos=boletos,
        boleto_aberto=aberto,
    )

@app.route('/funcionario')
@login_required('funcionario')
def dashboard_funcionario():
    busca = request.args.get('cliente', '').strip()
    return render_template(
        'funcionario/dashboard_funcionario.html',
        usuario=session['usuario'],
        resumo=resumo_funcionario(),
        clientes=clientes_funcionario(busca),
        busca=busca,
    )

@app.route('/admin')
@login_required('admin')
def dashboard_admin():
    return render_template(
        'admin/dashboard_admin.html',
        usuario=session['usuario'],
        resumo=resumo_admin(),
    )

if __name__ == '__main__':
    app.run(debug=True)
