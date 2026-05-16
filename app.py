from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

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


@app.route('/contato', methods=['GET', 'POST'])
def contato():
    enviado = False
    erro_envio = ''
    contato_enviado = {}

    if request.method == 'POST':
        contato_enviado = {
            'nome': request.form.get('nome', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telefone': request.form.get('telefone', '').strip(),
            'assunto': request.form.get('assunto', '').strip(),
            'mensagem': request.form.get('mensagem', '').strip(),
        }
        try:
            salvar_contato(contato_enviado)
            enviado = True
        except Exception as erro:
            erro_envio = str(erro)

    return render_template(
        'contato.html',
        enviado=enviado,
        erro_envio=erro_envio,
        contato_enviado=contato_enviado
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    tipo = request.args.get('tipo', 'cliente')

    if request.method == 'POST':
        tipo = request.form.get('tipo', 'cliente')
        destinos = {
            'cliente': 'dashboard_cliente',
            'funcionario': 'dashboard_funcionario',
            'admin': 'dashboard_admin',
        }
        return redirect(url_for(destinos.get(tipo, 'dashboard_cliente')))

    return render_template('login.html', tipo=tipo)

@app.route('/cliente')
def dashboard_cliente():
    return render_template('cliente/dashboard_cliente.html')

@app.route('/funcionario')
def dashboard_funcionario():
    return render_template('funcionario/dashboard_funcionario.html')

@app.route('/admin')
def dashboard_admin():
    return render_template('admin/dashboard_admin.html')

if __name__ == '__main__':
    app.run(debug=True)
