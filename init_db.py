import mysql.connector
import os
from dotenv import load_dotenv
import logging

def init_database():
    """Инициализация базы данных"""
    load_dotenv()
    
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Подключение к MySQL
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        cursor = connection.cursor()
        
        # Создание базы данных
        db_name = os.getenv('DB_NAME')
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")
        
        # Создание таблиц
        tables = {
            'signals': """
                CREATE TABLE IF NOT EXISTS signals (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    signal_type VARCHAR(10) NOT NULL,
                    price DECIMAL(20,8) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    executed BOOLEAN DEFAULT FALSE,
                    success BOOLEAN DEFAULT NULL,
                    profit_loss DECIMAL(20,8) DEFAULT NULL
                )
            """,
            'trades': """
                CREATE TABLE IF NOT EXISTS trades (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    entry_price DECIMAL(20,8) NOT NULL,
                    exit_price DECIMAL(20,8),
                    quantity DECIMAL(20,8) NOT NULL,
                    entry_time DATETIME NOT NULL,
                    exit_time DATETIME,
                    profit_loss DECIMAL(20,8),
                    success BOOLEAN
                )
            """,
            'performance': """
                CREATE TABLE IF NOT EXISTS performance (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL,
                    starting_balance DECIMAL(20,8) NOT NULL,
                    ending_balance DECIMAL(20,8) NOT NULL,
                    profit_loss DECIMAL(20,8) NOT NULL,
                    trade_count INT NOT NULL
                )
            """
        }
        
        # Создание каждой таблицы
        for table_name, table_sql in tables.items():
            logger.info(f"Creating table {table_name}...")
            cursor.execute(table_sql)
            
        connection.commit()
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise
        
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def main():
    """Основная функция для инициализации базы данных"""
    try:
        init_database()
        print("Database initialization completed successfully!")
    except Exception as e:
        print(f"Error during database initialization: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
