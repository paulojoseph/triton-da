#!/bin/bash
# Copia a solução Python limpa e homologada diretamente para o arquivo alvo
cp "$(dirname "$0")/solve.py" /app/aggregator.py

# Executa para gerar o JSON inicial esperado pela esteira
python3 /app/aggregator.py