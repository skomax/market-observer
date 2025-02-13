import os
import sys
import logging
from src.main import TradingBot
from src.config_manager import ConfigManager
import argparse

# Добавляем текущую директорию в PYTHONPATH
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

def create_directories():
    """Создание необходимых директорий"""
    directories = ['logs', 'data', 'database']
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)

def parse_arguments():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description='SMS Trade Bot')
    parser.add_argument(
        '--mode', 
        choices=['test', 'real'],
        default='test',
        help='Trading mode (test/real)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    parser.add_argument(
        '--no-web',
        action='store_true',
        help='Disable web interface'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to custom config file'
    )
    return parser.parse_args()

def main():
    """Основная функция запуска бота"""
    # Парсинг аргументов
    args = parse_arguments()
    
    # Создание директорий
    create_directories()
    
    # Настройка логирования
    setup_logging()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting SMS Trade Bot...")
    
    try:
        # Загрузка конфигурации
        config = ConfigManager()
        if args.config:
            config.load_custom_config(args.config)
        
        # Установка режима работы
        os.environ['TRADING_MODE'] = args.mode
        
        # Установка состояния веб-интерфейса
        if args.no_web:
            os.environ['WEB_INTERFACE_ENABLED'] = 'false'
        
        logger.info(f"Trading mode: {args.mode}")
        logger.info(f"Web interface: {'disabled' if args.no_web else 'enabled'}")
        
        # Проверка наличия необходимых переменных окружения
        required_vars = [
            f'BINANCE_API_KEY_{args.mode.upper()}',
            f'BINANCE_SECRET_KEY_{args.mode.upper()}',
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_CHANNEL_ID'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        # Создание и запуск бота
        bot = TradingBot()
        if not hasattr(bot, 'run'):
            raise AttributeError(f"Bot instance does not have 'run' method. Available methods: {dir(bot)}")
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
        logger.exception("Full traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main()
