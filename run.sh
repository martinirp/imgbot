#!/bin/bash
# Configura o display para não dar erro no Linux
export DISPLAY=:0

# Roda o script forçando o Python do ambiente virtual
./venv/bin/python main.py
