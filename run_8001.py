# Importa a aplicacao Flask preparada no arquivo principal.
from app import app


# Este bloco so e executado quando iniciamos este arquivo diretamente.
# A porta 8001 evita conflito com uma instancia antiga que use a porta 8000.
if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=8001)
