# Posto Nova Rota

Site e protótipo do sistema RotaFácil para o Posto Nova Rota.

## Como executar

1. Instale as dependências:

```powershell
pip install -r requirements.txt
```

2. Inicie o Flask:

```powershell
python app.py
```

3. Acesse no navegador:

```text
http://127.0.0.1:5000
```

## Telas disponíveis

- `/` - página institucional
- `/login` - seleção de perfil e login
- `/cliente` - área do cliente
- `/funcionario` - área do funcionário
- `/admin` - dashboard administrativo

## Formulário de contato

Por enquanto, o formulário salva as mensagens em:

```text
logs/contatos.log
```

Assim não é necessário configurar senha de e-mail durante o desenvolvimento.
