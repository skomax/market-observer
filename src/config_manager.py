import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        load_dotenv()
        self.config = {}
        self.load_config()

    def load_config(self):
        """Загрузка конфигурации из .env файла"""
        try:
            self.config = {
                'trading_mode': os.getenv('TRADING_MODE', 'test'),
                'trading_pairs': os.getenv('TRADING_PAIRS', '').split(','),
                'api_keys': {
                    'test': {
                        'api_key': os.getenv('BINANCE_API_KEY_TEST'),
                        'api_secret': os.getenv('BINANCE_SECRET_KEY_TEST')
                    },
                    'real': {
                        'api_key': os.getenv('BINANCE_API_KEY_REAL'),
                        'api_secret': os.getenv('BINANCE_SECRET_KEY_REAL')
                    }
                },
                'telegram': {
                    'bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
                    'channel_id': os.getenv('TELEGRAM_CHANNEL_ID')
                },
                'web': {
                    'enabled': os.getenv('WEB_INTERFACE_ENABLED', 'true').lower() == 'true',
                    'username': os.getenv('WEB_USERNAME'),
                    'password': os.getenv('WEB_PASSWORD'),
                    'port': int(os.getenv('WEB_PORT', 3000))
                },
                'database': {
                    'host': os.getenv('DB_HOST'),
                    'name': os.getenv('DB_NAME'),
                    'user': os.getenv('DB_USER'),
                    'password': os.getenv('DB_PASSWORD')
                },
                'logging': {
                    'level': os.getenv('LOG_LEVEL', 'INFO')
                }
            }
            
            self.validate_config()
            
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            raise

    def validate_config(self):
        """Проверка корректности конфигурации"""
        required_fields = [
            'trading_mode',
            'trading_pairs',
            'api_keys',
            'telegram.bot_token',
            'telegram.channel_id'
        ]
        
        for field in required_fields:
            if not self.get_nested_value(field):
                raise ValueError(f"Missing required configuration: {field}")

    def get_nested_value(self, key_path):
        """Получение вложенного значения из конфигурации"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
                
        return value

    def get_api_credentials(self):
        """Получение текущих API-ключей"""
        mode = self.config['trading_mode']
        return self.config['api_keys'][mode]

    def update_config(self, key, value):
        """Обновление значения в конфигурации"""
        try:
            keys = key.split('.')
            current = self.config
            
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            
            current[keys[-1]] = value
            
        except Exception as e:
            logger.error(f"Error updating configuration: {str(e)}")
