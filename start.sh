#!/bin/bash

# Активация виртуального окружения (если используется)
# source venv/bin/activate

# Проверка наличия необходимых директорий
mkdir -p logs
mkdir -p data
mkdir -p database

# Установка зависимостей
pip install -r requirements.txt

# Инициализация базы данных
python init_db.py

# Запуск бота
python start.py --mode test
