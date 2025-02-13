from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd
import logging
import time
from threading import Lock
import asyncio
import json
from typing import Dict, Optional
from binance import AsyncClient, BinanceSocketManager

logger = logging.getLogger(__name__)

class BinanceHandler:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet
        self.kline_data: Dict[str, dict] = {}
        self.lock = Lock()
        self.last_request_time: Dict[str, float] = {}
        self.request_limit = 1.0  # минимальный интервал между запросами в секундах
        
        # Кэш для данных
        self.cached_data: Dict[str, tuple] = {}
        self.cache_timeout = 60  # время жизни кэша в секундах
        
        # WebSocket компоненты
        self.async_client = None
        self.bm = None
        self.ws_connections = {}

    async def init_socket_manager(self):
        """Инициализация WebSocket менеджера"""
        try:
            if not self.async_client:
                self.async_client = await AsyncClient.create(
                    api_key=self.client.API_KEY,
                    api_secret=self.client.API_SECRET,
                    testnet=self.testnet
                )
            if not self.bm:
                self.bm = BinanceSocketManager(self.async_client)
        except Exception as e:
            logger.error(f"Error initializing socket manager: {str(e)}")

    async def start_symbol_ticker_socket(self, symbol: str):
        """Запуск WebSocket для получения тикеров"""
        try:
            if symbol in self.ws_connections:
                return

            await self.init_socket_manager()

            async def message_handler(msg):
                try:
                    if msg.get('e') == 'kline':
                        with self.lock:
                            self.kline_data[symbol] = {
                                'price': float(msg['k']['c']),
                                'volume': float(msg['k']['v']),
                                'timestamp': msg['E']
                            }
                except Exception as e:
                    logger.error(f"Error in socket message handler: {str(e)}")

            # Создаем и запускаем socket
            kline_socket = self.bm.kline_socket(symbol=symbol)
            
            # Запускаем обработку сообщений
            async with kline_socket as stream:
                while True:
                    msg = await stream.recv()
                    await message_handler(msg)

        except Exception as e:
            logger.error(f"Error starting symbol ticker socket: {str(e)}")

    def _wait_for_request(self, endpoint: str):
        """Ожидание перед запросом для соблюдения лимитов"""
        current_time = time.time()
        if endpoint in self.last_request_time:
            time_passed = current_time - self.last_request_time[endpoint]
            if time_passed < self.request_limit:
                time.sleep(self.request_limit - time_passed)
        self.last_request_time[endpoint] = current_time

    def get_historical_data(self, symbol: str, interval: str = '1h', limit: int = 100) -> Optional[pd.DataFrame]:
        """Получение исторических данных с кэшированием"""
        cache_key = f"{symbol}_{interval}_{limit}"
        current_time = time.time()

        # Проверка кэша
        if cache_key in self.cached_data:
            cache_time, data = self.cached_data[cache_key]
            if current_time - cache_time < self.cache_timeout:
                return data

        try:
            self._wait_for_request('klines')
            
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            # Сохранение в кэш
            self.cached_data[cache_key] = (current_time, df)
            
            return df
            
        except BinanceAPIException as e:
            logger.error(f"Error getting historical data: {str(e)}")
            return None

    def get_account_balance(self) -> float:
        """Получение баланса аккаунта"""
        try:
            self._wait_for_request('account')
            
            account = self.client.get_account()
            usdt_balance = float(next(
                (balance['free'] for balance in account['balances']
                 if balance['asset'] == 'USDT'),
                0
            ))
            return usdt_balance
            
        except BinanceAPIException as e:
            logger.error(f"Error getting account balance: {str(e)}")
            return 0.0

    def place_order(self, symbol: str, side: str, quantity: float) -> Optional[dict]:
        """Размещение ордера"""
        try:
            self._wait_for_request('order')
            
            order = self.client.create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            return order
            
        except BinanceAPIException as e:
            logger.error(f"Error placing order: {str(e)}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Получение текущей цены"""
        try:
            # Сначала пробуем получить из WebSocket
            if symbol in self.kline_data:
                return self.kline_data[symbol]['price']

            # Если нет данных из WebSocket, делаем REST запрос
            self._wait_for_request('ticker')
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
            
        except BinanceAPIException as e:
            logger.error(f"Error getting current price: {str(e)}")
            return None

    async def cleanup(self):
        """Очистка ресурсов"""
        try:
            if self.bm:
                await self.bm.close()
            if self.async_client:
                await self.async_client.close_connection()
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
