import logging
from datetime import datetime, timedelta
import time
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class TradingManager:
    def __init__(self):
        load_dotenv()
        
        # Загрузка настроек сигналов
        self.signal_check_interval = int(os.getenv('SIGNAL_CHECK_INTERVAL', 300))
        self.signal_minimum_interval = int(os.getenv('SIGNAL_MINIMUM_INTERVAL', 3600))
        
        # Загрузка настроек ордеров
        self.order_cooldown = int(os.getenv('ORDER_COOLDOWN', 1800))
        self.max_daily_orders = int(os.getenv('MAX_DAILY_ORDERS', 10))
        self.trading_hours_start = int(os.getenv('TRADING_HOURS_START', 9))
        self.trading_hours_end = int(os.getenv('TRADING_HOURS_END', 21))
        self.trading_days = [int(x) for x in os.getenv('TRADING_DAYS', '1,2,3,4,5').split(',')]
        
        # Хранение последних сигналов и ордеров
        self.last_signals = {}
        self.last_orders = {}
        self.daily_orders_count = 0
        self.last_reset_date = datetime.now().date()
        
        logger.info(f"Trading Manager initialized with following settings:")
        logger.info(f"Signal check interval: {self.signal_check_interval} seconds")
        logger.info(f"Signal minimum interval: {self.signal_minimum_interval} seconds")
        logger.info(f"Order cooldown: {self.order_cooldown} seconds")
        logger.info(f"Max daily orders: {self.max_daily_orders}")
        logger.info(f"Trading hours: {self.trading_hours_start}:00 - {self.trading_hours_end}:00")
        logger.info(f"Trading days: {self.trading_days}")

    def can_check_signals(self, symbol):
        """Проверка возможности проверки сигналов"""
        current_time = datetime.now()
        
        # Проверка последнего сигнала
        if symbol in self.last_signals:
            time_since_last = (current_time - self.last_signals[symbol]).total_seconds()
            if time_since_last < self.signal_check_interval:
                logger.debug(f"Signal check for {symbol} skipped: cooldown period not passed")
                return False
        
        if not self._is_trading_time():
            logger.debug(f"Signal check for {symbol} skipped: outside trading hours")
            return False
        
        return True

    def can_place_order(self, symbol):
        """Проверка возможности размещения ордера"""
        current_time = datetime.now()
        current_date = current_time.date()
        
        # Сброс счетчика ордеров при новом дне
        if current_date != self.last_reset_date:
            logger.info("Resetting daily order counter")
            self.daily_orders_count = 0
            self.last_reset_date = current_date
        
        # Проверка дневного лимита ордеров
        if self.daily_orders_count >= self.max_daily_orders:
            logger.info(f"Order for {symbol} skipped: daily limit reached")
            return False
        
        # Проверка кулдауна ордеров
        if symbol in self.last_orders:
            time_since_last = (current_time - self.last_orders[symbol]).total_seconds()
            if time_since_last < self.order_cooldown:
                logger.debug(f"Order for {symbol} skipped: cooldown period not passed")
                return False
        
        if not self._is_trading_time():
            logger.debug(f"Order for {symbol} skipped: outside trading hours")
            return False
        
        return True

    def _is_trading_time(self):
        """Проверка торгового времени"""
        current_time = datetime.now()
        current_hour = current_time.hour
        current_weekday = current_time.isoweekday()
        
        # Проверка дня недели
        if current_weekday not in self.trading_days:
            return False
        
        # Проверка времени
        if not (self.trading_hours_start <= current_hour < self.trading_hours_end):
            return False
            
        return True

    def register_signal(self, symbol):
        """Регистрация сигнала"""
        current_time = datetime.now()
        self.last_signals[symbol] = current_time
        logger.info(f"Signal registered for {symbol} at {current_time}")

    def register_order(self, symbol):
        """Регистрация ордера"""
        current_time = datetime.now()
        self.last_orders[symbol] = current_time
        self.daily_orders_count += 1
        logger.info(f"Order registered for {symbol} at {current_time}. Daily total: {self.daily_orders_count}")

    def get_next_signal_time(self, symbol):
        """Получение времени следующего возможного сигнала"""
        if symbol not in self.last_signals:
            return datetime.now()
            
        next_time = self.last_signals[symbol] + timedelta(seconds=self.signal_minimum_interval)
        return next_time

    def get_next_order_time(self, symbol):
        """Получение времени следующего возможного ордера"""
        if symbol not in self.last_orders:
            return datetime.now()
            
        next_time = self.last_orders[symbol] + timedelta(seconds=self.order_cooldown)
        return next_time

    def get_trading_status(self):
        """Получение статуса торговли"""
        status = {
            'daily_orders': self.daily_orders_count,
            'max_daily_orders': self.max_daily_orders,
            'trading_hours': f"{self.trading_hours_start}:00 - {self.trading_hours_end}:00",
            'is_trading_time': self._is_trading_time(),
            'next_reset': (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0),
            'trading_pairs_status': {}
        }
        
        # Добавляем статус для каждой пары
        for symbol in self.last_signals.keys():
            status['trading_pairs_status'][symbol] = {
                'next_signal': self.get_next_signal_time(symbol),
                'next_order': self.get_next_order_time(symbol) if symbol in self.last_orders else None,
                'signals_today': sum(1 for time in [self.last_signals[symbol]] if time.date() == datetime.now().date()),
                'orders_today': sum(1 for time in [self.last_orders.get(symbol)] if time and time.date() == datetime.now().date())
            }
        
        return status
