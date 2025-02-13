import os
import logging
import threading
import time
import asyncio
import pandas as pd
import numpy as np
from binance import AsyncClient, BinanceSocketManager
from src.binance_handler import BinanceHandler
from src.telegram_handler import TelegramHandler
from src.database_handler import DatabaseHandler
from src.web_interface import start_web_server
from src.risk_manager import RiskManager
from src.trading_manager import TradingManager
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Dict, Optional
from src.prediction_manager import PredictionManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self):
        # Добавляем инициализацию списка WebSocket соединений
        self.ws_connections = []
    
        load_dotenv()
        self.trading_mode = os.getenv('TRADING_MODE')
        self.trading_pairs = os.getenv('TRADING_PAIRS').split(',')
        self.check_interval = int(os.getenv('CHECK_INTERVAL', 60))
        self.start_time = datetime.now()
        
        # Инициализация Предсказаний
        self.enable_predictions = os.getenv('ENABLE_PREDICTIONS', 'false').lower() == 'true'
        self.prediction_interval = int(os.getenv('PREDICTION_INTERVAL', '300'))
        self.prediction_horizon = int(os.getenv('PREDICTION_HORIZON', '900'))
        self.prediction_min_change = float(os.getenv('PREDICTION_MIN_CHANGE', '0.5'))
        self.prediction_cooldown = int(os.getenv('PREDICTION_COOLDOWN', '900'))
        self.enable_prediction_accuracy = os.getenv('ENABLE_PREDICTION_ACCURACY', 'true').lower() == 'true'
        self.accuracy_notification_threshold = float(os.getenv('ACCURACY_NOTIFICATION_THRESHOLD', '1.0'))
        self.prediction_manager = PredictionManager()
        self.last_prediction_time = {}
        
        # Загрузка настроек индикаторов
        self.indicator_settings = {
            'ema_short': int(os.getenv('EMA_SHORT', 3)),
            'ema_long': int(os.getenv('EMA_LONG', 7)),
            'rsi_period': int(os.getenv('RSI_PERIOD', 5)),
            'rsi_overbought': int(os.getenv('RSI_OVERBOUGHT', 70)),
            'rsi_oversold': int(os.getenv('RSI_OVERSOLD', 30)),
            'macd_fast': int(os.getenv('MACD_FAST', 8)),
            'macd_slow': int(os.getenv('MACD_SLOW', 17)),
            'macd_signal': int(os.getenv('MACD_SIGNAL', 7)),
            'bb_period': int(os.getenv('BB_PERIOD', 10)),
            'bb_std': int(os.getenv('BB_STD', 2)),
            'momentum_period': int(os.getenv('MOMENTUM_PERIOD', 3))
        }
    
        # Загрузка торговых настроек
        self.trading_settings = {
            'max_position_time': int(os.getenv('MAX_POSITION_TIME', 10)),
            'max_risk_percent': float(os.getenv('MAX_RISK_PERCENT', 5)),
            'min_signal_strength': float(os.getenv('MIN_SIGNAL_STRENGTH', 50)),
            'stop_loss_percent': float(os.getenv('STOP_LOSS_PERCENT', 1.0)),
            'take_profit_percent': float(os.getenv('TAKE_PROFIT_PERCENT', 2.0)),
            'enable_trailing_stop': os.getenv('ENABLE_TRAILING_STOP', 'true').lower() == 'true',
            'trailing_stop_percent': float(os.getenv('TRAILING_STOP_PERCENT', 0.5))
        }

        # Настройки уведомлений
        self.notification_settings = {
            'send_regular_updates': os.getenv('SEND_REGULAR_UPDATES', 'true').lower() == 'true',
            'min_price_change': float(os.getenv('MIN_PRICE_CHANGE_PERCENT', '0.1')),
            'min_rsi_change': float(os.getenv('MIN_RSI_CHANGE', '3')),
            'notification_cooldown': int(os.getenv('NOTIFICATION_COOLDOWN', '60')),
            'last_notification_time': {},
            'last_analysis': {}
        }
        
        self.binance = BinanceHandler(
            api_key=os.getenv(f'BINANCE_API_KEY_{self.trading_mode.upper()}'),
            api_secret=os.getenv(f'BINANCE_SECRET_KEY_{self.trading_mode.upper()}'),
            testnet=(self.trading_mode == 'test')
        )
        
        self.telegram = TelegramHandler(
            token=os.getenv('TELEGRAM_BOT_TOKEN'),
            channel_id=os.getenv('TELEGRAM_CHANNEL_ID')
        )
        
        self.db = DatabaseHandler()
        self.risk_manager = RiskManager()
        self.trading_manager = TradingManager()
        
        self.starting_balance = None
        self.current_balance = None
        self.active_trades = {}
        self.last_signals = []
        
        # WebSocket компоненты
        self.ws_client = None
        self.ws_manager = None
        self.price_cache = {}
        self.loop = asyncio.new_event_loop()
        self.analysis_lock = asyncio.Lock()
        asyncio.set_event_loop(self.loop)
        
        # Инициализация исторических данных
        self.initialize_price_cache()

        # Изменяем инициализацию event loop
        self.loop = None
        self.main_task = None
        self.should_run = True
        self.last_daily_summary = datetime.now().date()

        logger.info(f"Trading Bot initialized in {self.trading_mode} mode")
        logger.info(f"Trading pairs: {', '.join(self.trading_pairs)}")

        # Отправка тестового сообщения при запуске
        self.send_startup_message()
        
    async def check_prediction_accuracy(self):
        """Проверка точности прогнозов"""
        try:
            current_time = datetime.now()
            
            for symbol in self.trading_pairs:
                if symbol not in self.prediction_manager.pending_predictions:
                    continue
                    
                predictions = self.prediction_manager.pending_predictions[symbol]
                if not predictions:
                    continue
                
                # Проверяем прогнозы, время которых наступило
                while predictions and predictions[0]['check_time'] <= current_time:
                    pred = predictions.pop(0)  # Забираем самый старый прогноз
                    
                    # Получаем текущую цену
                    if symbol in self.price_cache and self.price_cache[symbol]:
                        actual_price = float(self.price_cache[symbol][-1]['close'])
                        
                        # Проверяем точность
                        message = self.prediction_manager.get_prediction_accuracy_message(
                            pred, actual_price, pred['timeframe']
                        )
                        
                        if message:
                            # Вычисляем отклонение
                            deviation = abs(actual_price - pred['predicted_price'])
                            deviation_percent = (deviation / pred['predicted_price']) * 100
                            
                            # Отправляем сообщение если отклонение превышает порог
                            if deviation_percent >= self.accuracy_notification_threshold:
                                await self.telegram.send_custom_message(message, "PREDICTION_ACCURACY")
                                
                            # Сохраняем результат в базу данных
                            self.db.save_prediction_accuracy({
                                'symbol': symbol,
                                'predicted_price': pred['predicted_price'],
                                'actual_price': actual_price,
                                'deviation_percent': deviation_percent,
                                'timeframe': pred['timeframe'],
                                'check_time': current_time,
                                'within_range': pred['range_low'] <= actual_price <= pred['range_high']
                            })
                
        except Exception as e:
            logger.error(f"Error checking prediction accuracy: {str(e)}")
        
    async def generate_and_send_predictions(self):
        """Генерация и отправка прогнозов"""
        try:
            current_time = datetime.now()
            
            # Сначала проверяем точность предыдущих прогнозов
            if self.enable_prediction_accuracy:
                await self.check_prediction_accuracy()
            
            for symbol in self.trading_pairs:
                try:
                    # Проверяем время последнего прогноза
                    last_time = self.last_prediction_time.get(symbol, datetime.min)
                    time_since_last = (current_time - last_time).total_seconds()
                    
                    # Если не прошло достаточно времени, пропускаем
                    if time_since_last < self.prediction_cooldown:
                        continue

                    if symbol in self.price_cache and len(self.price_cache[symbol]) > 0:
                        current_price = float(self.price_cache[symbol][-1]['close'])
                        
                        # Проверяем, есть ли существенное изменение цены
                        if not self.prediction_manager.is_significant_change(
                            symbol, current_price, self.prediction_min_change
                        ):
                            continue

                        # Генерируем прогноз
                        prediction = self.prediction_manager.get_prediction(
                            symbol,
                            self.price_cache[symbol],
                            timeframes=[5, 15]
                        )

                        if prediction:
                            # Сохраняем прогноз в базу данных
                            self.db.save_prediction(prediction)
                            # Сохраняем прогноз для последующей проверки
                            self.prediction_manager.store_prediction(symbol, prediction)
                            
                            # Форматируем и отправляем сообщение
                            message = self.prediction_manager.format_prediction_message(prediction)
                            if message:
                                self.telegram.send_custom_message(message, "PREDICTION")
                                self.last_prediction_time[symbol] = current_time
                                logger.info(f"Sent prediction for {symbol}")

                except Exception as e:
                    logger.error(f"Error processing prediction for {symbol}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error generating predictions: {str(e)}")
            
    async def main_loop(self):
        # В основном цикле добавляем:
        while self.should_run:
            try:
                self.manage_active_trades()
                self.update_balance()
                
                # Добавляем генерацию прогнозов если включено
                if self.enable_predictions:
                    await self.generate_and_send_predictions()
                
                if os.getenv('WEB_INTERFACE_ENABLED', 'true').lower() != 'true':
                    self.display_console_info()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in main loop iteration: {str(e)}")
                await asyncio.sleep(60)
        
    def initialize_price_cache(self):
        """Инициализация кэша цен историческими данными"""
        try:
            for pair in self.trading_pairs:
                historical_data = self.binance.get_historical_data(pair, interval='1m', limit=100)
                
                if historical_data is not None and not historical_data.empty:
                    self.price_cache[pair] = []
                    
                    for index, row in historical_data.iterrows():
                        cache_item = {
                            'timestamp': index,
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': float(row['volume']),
                            'symbol': pair
                        }
                        self.price_cache[pair].append(cache_item)
                    
                    logger.info(f"Initialized price cache for {pair} with {len(self.price_cache[pair])} entries")
                else:
                    logger.warning(f"Could not initialize price cache for {pair}")
                    
        except Exception as e:
            logger.error(f"Error initializing price cache: {str(e)}")

    async def start_socket(self, socket, message_handler):
        """Запуск отдельного сокета"""
        try:
            async with socket as connection:
                self.ws_connections.append(connection)
                
                while self.should_run:
                    try:
                        msg = await connection.recv()
                        await message_handler(msg)
                    except asyncio.CancelledError:
                        logger.info("Socket connection cancelled")
                        break
                    except Exception as e:
                        logger.error(f"Error in socket stream: {str(e)}")
                        if self.should_run:
                            await asyncio.sleep(5)
                            continue
                        break
                        
        except Exception as e:
            logger.error(f"Error in socket stream: {str(e)}")
        finally:
            try:
                if connection in self.ws_connections:
                    self.ws_connections.remove(connection)
            except Exception as e:
                logger.error(f"Error removing socket connection: {str(e)}")
            
    def display_console_info(self):
        """Отображение информации о состоянии бота в консоли"""
        try:
            # Очистка консоли
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Текущее время
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Заголовок
            print("=" * 50)
            print(f"Trading Bot Status ({self.trading_mode.upper()} mode)")
            print("=" * 50)
            
            # Общая информация
            print(f"\nCurrent Time: {current_time}")
            print(f"Running Time: {datetime.now() - self.start_time}")
            
            # Информация о балансе
            print("\nBalance Information:")
            print(f"Starting Balance: {self.starting_balance:.2f} USDT")
            print(f"Current Balance: {self.current_balance:.2f} USDT")
            
            if self.starting_balance > 0:
                profit_loss = self.current_balance - self.starting_balance
                profit_loss_percent = (profit_loss / self.starting_balance) * 100
                print(f"Total P/L: {profit_loss:.2f} USDT ({profit_loss_percent:.2f}%)")
            
            # Активные сделки
            print("\nActive Trades:")
            if self.active_trades:
                for symbol, trade in self.active_trades.items():
                    current_price = self.binance.get_current_price(symbol)
                    if current_price:
                        position_size = trade['quantity'] * trade['entry_price']
                        current_value = trade['quantity'] * current_price
                        unrealized_pnl = current_value - position_size
                        unrealized_pnl_percent = (unrealized_pnl / position_size) * 100
                        
                        print(f"\n{symbol}:")
                        print(f"  Type: {trade['type']}")
                        print(f"  Entry Price: {trade['entry_price']:.2f}")
                        print(f"  Current Price: {current_price:.2f}")
                        print(f"  Quantity: {trade['quantity']:.8f}")
                        print(f"  Unrealized P/L: {unrealized_pnl:.2f} USDT ({unrealized_pnl_percent:.2f}%)")
                        print(f"  Time in Trade: {datetime.now() - trade['timestamp']}")
            else:
                print("No active trades")
            
            # Мониторинг пар
            print("\nMonitored Pairs:")
            for pair in self.trading_pairs:
                if pair in self.price_cache and self.price_cache[pair]:
                    last_price = self.price_cache[pair][-1]['close']
                    print(f"{pair}: {last_price:.2f}")
            
            # Статистика риск-менеджера
            print("\nRisk Management Stats:")
            stats = self.risk_manager.get_stats()
            print(f"Win Rate: {stats.get('win_rate', 0):.2f}%")
            print(f"Average Win: {stats.get('avg_win', 0):.2f} USDT")
            print(f"Average Loss: {stats.get('avg_loss', 0):.2f} USDT")
            
            print("\n" + "=" * 50)
            
        except Exception as e:
            logger.error(f"Error displaying console info: {str(e)}")

    async def process_kline_message(self, msg):
        """Обработка сообщений WebSocket"""
        try:
            if not isinstance(msg, dict):
                logger.warning(f"Received invalid message format: {msg}")
                return
                
            symbol = msg.get('s')
            kline = msg.get('k')
            
            if not symbol or not kline:
                logger.warning(f"Missing required data in message: {msg}")
                return
                
            if kline.get('x'):  # если свеча закрыта
                price_data = {
                    'timestamp': pd.to_datetime(msg['E'], unit='ms'),
                    'open': float(kline['o']),
                    'high': float(kline['h']),
                    'low': float(kline['l']),
                    'close': float(kline['c']),
                    'volume': float(kline['v']),
                    'symbol': symbol
                }
                
                await self.update_realtime_data(price_data)
                
                cache_size = self.get_cache_size(symbol)
                logger.info(f"Current cache size for {symbol}: {cache_size}")
                
                if self.can_send_notification(symbol):
                    await self.analyze_realtime_data(symbol)
                    
        except Exception as e:
            logger.error(f"Error processing kline message: {str(e)}")
            logger.exception("Full traceback:")

    async def update_realtime_data(self, price_data):
        """Обновление данных в реальном времени"""
        try:
            symbol = price_data['symbol']
            
            if symbol not in self.price_cache:
                self.price_cache[symbol] = []
            
            self.price_cache[symbol].append(price_data)
            
            if len(self.price_cache[symbol]) > 100:
                self.price_cache[symbol] = self.price_cache[symbol][-100:]
            
            logger.info(f"Updated price cache for {symbol}. Cache size: {len(self.price_cache[symbol])}")
            
        except Exception as e:
            logger.error(f"Error updating realtime data: {str(e)}")

    def send_startup_message(self):
        """Отправка тестового сообщения при запуске"""
        try:
            logger.info("Preparing startup message...")
            startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            prices = {}
            for pair in self.trading_pairs:
                try:
                    current_price = self.binance.get_current_price(pair)
                    logger.info(f"Got price for {pair}: {current_price}")
                    if current_price:
                        prices[pair] = current_price
                except Exception as e:
                    logger.error(f"Error getting price for {pair}: {str(e)}")
                    prices[pair] = "Error getting price"

            message = (
                f"🤖 Bot Startup Message\n\n"
                f"Status: Bot Successfully Started\n"
                f"Time: {startup_time}\n"
                f"Mode: {self.trading_mode.upper()}\n\n"
                f"Current Prices:\n"
            )
            
            for pair, price in prices.items():
                if isinstance(price, (int, float)):
                    message += f"• {pair}: {price:.8f}\n"
                else:
                    message += f"• {pair}: {price}\n"

            message += (
                f"\nSettings:\n"
                f"• Signal Check Interval: {self.check_interval}s\n"
                f"• Risk Per Trade: {self.trading_settings['max_risk_percent']}%\n"
                f"• Min Signal Strength: {self.trading_settings['min_signal_strength']}%\n\n"
                f"Bot is now monitoring the market... 📊"
            )

            logger.info("Sending startup message...")
            result = self.telegram.send_custom_message(message, "INFO")
            
            if result:
                logger.info("Startup message sent successfully")
            else:
                logger.error("Failed to send startup message")
            
        except Exception as e:
            logger.error(f"Error sending startup message: {str(e)}")
            logger.exception("Full traceback:")
            
    async def analyze_realtime_data(self, symbol: str):
        """Анализ данных в реальном времени"""
        try:
            logger.info(f"Starting analysis for {symbol}")
            
            if symbol not in self.price_cache or len(self.price_cache[symbol]) < 5:
                logger.info(f"Not enough data for {symbol}. Cache size: {len(self.price_cache.get(symbol, []))}")
                return
            
            # Создание DataFrame из кэшированных данных
            df = pd.DataFrame(self.price_cache[symbol])
            logger.debug(f"Initial DataFrame shape: {df.shape}")
            logger.debug(f"Initial columns: {df.columns.tolist()}")
            
            if df.empty:
                logger.warning(f"Empty DataFrame for {symbol}")
                return
                
            df.set_index('timestamp', inplace=True)
            
            # Расчет индикаторов
            data = self.calculate_scalping_indicators(df)
            
            # Проверка наличия индикаторов
            required_indicators = ['EMA5', 'EMA13', 'RSI', 'MACD', 'Signal_Line', 
                                 'BB_middle', 'BB_upper', 'BB_lower', 'Momentum']
            if not all(indicator in data.columns for indicator in required_indicators):
                logger.error(f"Missing indicators after calculation. Available: {data.columns}")
                return
                
            last_row = data.iloc[-1]
            prev_row = data.iloc[-2] if len(data) > 1 else None
            
            # Проверка объема
            volume_ma = df['volume'].rolling(window=20).mean()
            current_volume = df['volume'].iloc[-1]
            volume_increase = current_volume > volume_ma.iloc[-1] * 1.2
            
            logger.debug(f"Volume analysis for {symbol}:")
            logger.debug(f"Current volume: {current_volume}")
            logger.debug(f"Average volume: {volume_ma.iloc[-1]}")
            logger.debug(f"Volume increase: {volume_increase}")
            
            # Проверяем существенные изменения
            significant_change = False
            last_analysis = self.notification_settings['last_analysis'].get(symbol, {})
            
            if last_analysis:
                price_change = abs((last_row['close'] - last_analysis.get('price', 0)) / 
                                 last_analysis.get('price', 1) * 100)
                rsi_change = abs(last_row['RSI'] - last_analysis.get('rsi', 0))
                trend_change = (last_row['EMA5'] > last_row['EMA13']) != last_analysis.get('trend_up', False)
                
                logger.debug(f"Changes for {symbol}:")
                logger.debug(f"Price change: {price_change:.2f}% (min: {self.notification_settings['min_price_change']}%)")
                logger.debug(f"RSI change: {rsi_change:.2f} (min: {self.notification_settings['min_rsi_change']})")
                logger.debug(f"Trend change: {trend_change}")
                
                significant_change = (
                    price_change > self.notification_settings['min_price_change'] or
                    rsi_change > self.notification_settings['min_rsi_change'] or
                    trend_change
                )
            
            # Сохраняем текущие значения для следующего сравнения
            self.notification_settings['last_analysis'][symbol] = {
                'price': last_row['close'],
                'rsi': last_row['RSI'],
                'trend_up': last_row['EMA5'] > last_row['EMA13']
            }
            
            # Расширенное логирование технических индикаторов
            logger.debug(f"Technical analysis for {symbol}:")
            logger.debug(f"Current price: {last_row['close']}")
            logger.debug(f"EMA5: {last_row['EMA5']}")
            logger.debug(f"EMA13: {last_row['EMA13']}")
            logger.debug(f"RSI: {last_row['RSI']}")
            logger.debug(f"MACD: {last_row['MACD']}")
            logger.debug(f"Signal Line: {last_row['Signal_Line']}")
            logger.debug(f"Momentum: {last_row['Momentum']}")
            
            # Проверяем условия для анализа
            if volume_increase and significant_change:
                logger.info(f"Volume and significant change detected for {symbol}")
                
                # Получаем сигналы
                signals = await self.analyze_scalping_signals(data, symbol)
                
                if signals:
                    logger.info(f"Found {len(signals)} trading signals for {symbol}")
                    for signal in signals:
                        logger.debug(f"Signal details: {signal}")
                    await self.process_signals(signals, symbol)
                else:
                    logger.debug(f"No trading signals generated for {symbol}")
            
            # Отправляем уведомление если есть существенные изменения
            if significant_change and self.can_send_notification(symbol):
                logger.info(f"Sending analysis update for {symbol}")
                
                analysis_data = {
                    'current_price': float(last_row['close']),
                    'ema5': float(last_row['EMA5']),
                    'ema13': float(last_row['EMA13']),
                    'rsi': float(last_row['RSI']),
                    'macd': float(last_row['MACD']),
                    'signal_line': float(last_row['Signal_Line']),
                    'bb_upper': float(last_row['BB_upper']),
                    'bb_middle': float(last_row['BB_middle']),
                    'bb_lower': float(last_row['BB_lower']),
                    'momentum': float(last_row['Momentum']),
                    'volume': float(current_volume),
                    'avg_volume': float(volume_ma.iloc[-1]),
                    'signal_strength': self.calculate_signal_strength(last_row)
                }
                
                await self.telegram.send_analysis_update(symbol, analysis_data)
            
        except Exception as e:
            logger.error(f"Error analyzing realtime data: {str(e)}")
            logger.exception("Full traceback:")
            
    def can_send_notification(self, symbol: str) -> bool:
        """
        Проверяет, можно ли отправить уведомление для данного символа
        
        Args:
            symbol (str): Торговая пара
            
        Returns:
            bool: True если можно отправить уведомление, False если нет
        """
        try:
            current_time = datetime.now()
            last_notification_time = self.notification_settings['last_notification_time'].get(symbol)
            
            # Если это первое уведомление для символа
            if last_notification_time is None:
                self.notification_settings['last_notification_time'][symbol] = current_time
                return True
                
            # Проверяем, прошло ли достаточно времени с последнего уведомления
            time_since_last = (current_time - last_notification_time).total_seconds()
            cooldown = self.notification_settings['notification_cooldown']
            
            if time_since_last >= cooldown:
                self.notification_settings['last_notification_time'][symbol] = current_time
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking notification allowance for {symbol}: {str(e)}")
            return False

    def calculate_signal_strength(self, row):
        """Расчет силы сигнала"""
        try:
            conditions = [
                row['close'] > row['EMA5'],
                row['EMA5'] > row['EMA13'],
                35 < row['RSI'] < 65,  # Расширили диапазон
                row['MACD'] > row['Signal_Line'],
                row['close'] > row['BB_middle'],
                row['Momentum'] > 0
            ]
            
            # Добавим вес для более сильных сигналов
            weights = [1.2, 1.2, 1.0, 1.1, 1.0, 1.0]
            weighted_sum = sum(condition * weight for condition, weight in zip(conditions, weights))
            max_weighted_sum = sum(weights)
            
            return (weighted_sum / max_weighted_sum) * 100
            
        except Exception as e:
            logger.error(f"Error calculating signal strength: {str(e)}")
            return 0
            
    def update_balance(self):
        """Обновление баланса"""
        try:
            if self.starting_balance is None:
                starting_balance = self.binance.get_account_balance()
                if starting_balance is not None:
                    self.starting_balance = float(starting_balance)
                    logger.info(f"Starting balance set to: {self.starting_balance} USDT")
                else:
                    logger.error("Could not get starting balance")
                    self.starting_balance = 0.0

            current_balance = self.binance.get_account_balance()
            if current_balance is not None:
                self.current_balance = float(current_balance)
                logger.info(f"Current balance updated: {self.current_balance} USDT")
            else:
                logger.error("Could not get current balance")
                self.current_balance = self.starting_balance

            # Проверка изменения баланса
            if self.starting_balance > 0:
                profit_loss = self.current_balance - self.starting_balance
                profit_loss_percent = (profit_loss / self.starting_balance) * 100
                logger.info(f"Current P/L: {profit_loss:.2f} USDT ({profit_loss_percent:.2f}%)")

        except Exception as e:
            logger.error(f"Error updating balance: {str(e)}")
            if self.starting_balance is None:
                self.starting_balance = 0.0
            if self.current_balance is None:
                self.current_balance = self.starting_balance
    
    async def init_websockets(self):
        """Инициализация WebSocket подключений"""
        try:
            self.ws_client = await AsyncClient.create(
                api_key=os.getenv(f'BINANCE_API_KEY_{self.trading_mode.upper()}'),
                api_secret=os.getenv(f'BINANCE_SECRET_KEY_{self.trading_mode.upper()}'),
                testnet=(self.trading_mode == 'test')
            )
            self.ws_manager = BinanceSocketManager(self.ws_client)
            
            for pair in self.trading_pairs:
                symbol = pair.replace('/', '').lower()
                
                async def handle_socket_message(msg):
                    try:
                        if msg.get('e') == 'kline':
                            await self.process_kline_message(msg)
                    except Exception as e:
                        logger.error(f"Error in socket message handler: {str(e)}")
                
                kline_socket = self.ws_manager.kline_socket(symbol=symbol)
                asyncio.create_task(self.start_socket(kline_socket, handle_socket_message))
                logger.info(f"WebSocket initialized for {symbol}")
                
        except Exception as e:
            logger.error(f"Error initializing websockets: {str(e)}")
            
    def manage_active_trades(self):
        """Управление активными позициями"""
        try:
            for symbol in list(self.active_trades.keys()):
                trade = self.active_trades[symbol]
                
                # Получение текущей цены
                current_price = self.binance.get_current_price(symbol)
                if not current_price:
                    logger.warning(f"Could not get current price for {symbol}")
                    continue

                # Расчет текущей прибыли/убытка
                position_size = trade['quantity'] * trade['entry_price']
                current_value = trade['quantity'] * current_price
                unrealized_pnl = current_value - position_size
                unrealized_pnl_percent = (unrealized_pnl / position_size) * 100

                # Проверка времени в позиции
                time_in_trade = datetime.now() - trade['timestamp']
                
                # Логирование статуса позиции
                logger.info(f"Managing position for {symbol}:")
                logger.info(f"Time in trade: {time_in_trade}")
                logger.info(f"Current P/L: {unrealized_pnl:.2f} USDT ({unrealized_pnl_percent:.2f}%)")

                # Проверка условий выхода
                should_exit = False
                exit_reason = ""

                # Проверка стоп-лосса
                if current_price <= trade['stop_loss']:
                    should_exit = True
                    exit_reason = "Stop Loss triggered"
                
                # Проверка тейк-профита
                elif current_price >= trade['take_profit']:
                    should_exit = True
                    exit_reason = "Take Profit reached"
                
                # Проверка максимального времени в позиции
                elif time_in_trade > timedelta(minutes=self.trading_settings['max_position_time']):
                    should_exit = True
                    exit_reason = "Maximum position time exceeded"

                # Проверка условий выхода на основе технического анализа
                if not should_exit and symbol in self.price_cache:
                    df = pd.DataFrame(self.price_cache[symbol])
                    if not df.empty:
                        df.set_index('timestamp', inplace=True)
                        data = self.calculate_scalping_indicators(df)
                        last_row = data.iloc[-1]
                        
                        # Дополнительные условия выхода на основе индикаторов
                        if trade['type'] == 'BUY':
                            if (last_row['RSI'] > self.indicator_settings['rsi_overbought'] or
                                last_row['close'] < last_row['EMA5'] or
                                last_row['MACD'] < last_row['Signal_Line']):
                                should_exit = True
                                exit_reason = "Technical indicators suggest exit"

                # Выход из позиции если условия выхода выполнены
                if should_exit:
                    logger.info(f"Exiting position for {symbol}. Reason: {exit_reason}")
                    
                    # Размещение ордера на закрытие позиции
                    close_order = self.binance.place_order(
                        symbol=symbol,
                        side='SELL' if trade['type'] == 'BUY' else 'BUY',
                        quantity=trade['quantity']
                    )
                    
                    if close_order:
                        # Сохранение результатов сделки
                        self.db.save_trade(
                            symbol=symbol,
                            entry_price=trade['entry_price'],
                            exit_price=current_price,
                            quantity=trade['quantity'],
                            entry_time=trade['timestamp'],
                            exit_time=datetime.now(),
                            profit_loss=unrealized_pnl,
                            signal_strength=trade['signal_strength']
                        )
                        
                        # Обновление статистики риск-менеджера
                        self.risk_manager.update_trade_stats(
                            unrealized_pnl,
                            'WIN' if unrealized_pnl > 0 else 'LOSS'
                        )
                        
                        # Отправка уведомления о закрытии позиции
                        asyncio.create_task(self.telegram.send_trade_result(
                            symbol=symbol,
                            entry_price=trade['entry_price'],
                            exit_price=current_price,
                            profit_loss=unrealized_pnl,
                            duration=str(time_in_trade)
                        ))
                        
                        # Удаление торговли из активных
                        del self.active_trades[symbol]
                        logger.info(f"Position closed for {symbol}")
                    else:
                        logger.error(f"Failed to close position for {symbol}")

        except Exception as e:
            logger.error(f"Error managing active trades: {str(e)}")
            logger.exception("Full traceback:")
            
    def get_cache_size(self, symbol: str) -> int:
        """
        Получение размера кэша для указанного символа
        
        Args:
            symbol (str): Торговая пара
            
        Returns:
            int: Размер кэша для указанной пары
        """
        try:
            if symbol in self.price_cache:
                return len(self.price_cache[symbol])
            return 0
        except Exception as e:
            logger.error(f"Error getting cache size for {symbol}: {str(e)}")
            return 0
            
    def calculate_scalping_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Расчет индикаторов для скальпинга
        """
        try:
            # Создаем копию DataFrame
            data = df.copy()
            
            # Проверяем наличие необходимых колонок
            required_columns = ['close', 'high', 'low']
            if not all(col in data.columns for col in required_columns):
                logger.error(f"Missing required price columns. Available columns: {data.columns}")
                return df
                
            # Убедимся, что 'close' это числовой тип
            for col in required_columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
            
            logger.debug(f"Initial DataFrame shape: {data.shape}")
            logger.debug(f"Sample of close prices: {data['close'].head()}")
            
            # EMA
            data['EMA5'] = data['close'].ewm(span=self.indicator_settings['ema_short'], adjust=False).mean()
            data['EMA13'] = data['close'].ewm(span=self.indicator_settings['ema_long'], adjust=False).mean()
            
            # RSI
            delta = data['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.indicator_settings['rsi_period']).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.indicator_settings['rsi_period']).mean()
            rs = gain / loss
            data['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = data['close'].ewm(span=self.indicator_settings['macd_fast'], adjust=False).mean()
            exp2 = data['close'].ewm(span=self.indicator_settings['macd_slow'], adjust=False).mean()
            data['MACD'] = exp1 - exp2
            data['Signal_Line'] = data['MACD'].ewm(span=self.indicator_settings['macd_signal'], adjust=False).mean()
            
            # Bollinger Bands
            data['BB_middle'] = data['close'].rolling(window=self.indicator_settings['bb_period']).mean()
            bb_std = data['close'].rolling(window=self.indicator_settings['bb_period']).std()
            data['BB_upper'] = data['BB_middle'] + (bb_std * self.indicator_settings['bb_std'])
            data['BB_lower'] = data['BB_middle'] - (bb_std * self.indicator_settings['bb_std'])
            
            # Momentum
            data['Momentum'] = data['close'] - data['close'].shift(self.indicator_settings['momentum_period'])
            
            # Заполняем NaN значения
            data = data.fillna(method='bfill')
            
            # Проверяем расчет индикаторов
            calculated_indicators = ['EMA5', 'EMA13', 'RSI', 'MACD', 'Signal_Line', 
                                   'BB_middle', 'BB_upper', 'BB_lower', 'Momentum']
            
            for indicator in calculated_indicators:
                if indicator not in data.columns:
                    logger.error(f"Failed to calculate {indicator}")
                    return df
                if data[indicator].isna().any():
                    logger.warning(f"NaN values present in {indicator}")
                    
            logger.debug(f"Calculated indicators sample: {data[calculated_indicators].head()}")
            logger.info(f"Calculated indicators for {len(data)} candles")
            logger.debug(f"Available columns: {data.columns.tolist()}")
            
            return data
            
        except Exception as e:
            logger.error(f"Error calculating scalping indicators: {str(e)}")
            logger.exception("Full traceback:")
            return df
            
    async def analyze_scalping_signals(self, df: pd.DataFrame, symbol: str) -> list:
        """Анализ сигналов для скальпинга"""
        try:
            signals = []
            if df.empty:
                return signals
            
            # Проверяем наличие всех необходимых индикаторов
            required_indicators = ['EMA5', 'EMA13', 'RSI', 'MACD', 'Signal_Line', 
                                 'BB_middle', 'Momentum', 'close']
            
            if not all(indicator in df.columns for indicator in required_indicators):
                logger.error(f"Missing required indicators for {symbol}. Available columns: {df.columns}")
                return signals
            
            # Получаем последние две свечи для анализа
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else None

            # Проверяем, нет ли уже открытой позиции по этому символу
            if symbol in self.active_trades:
                logger.debug(f"Skip signal analysis - active trade exists for {symbol}")
                return signals

            # Расчет силы сигнала
            signal_strength = self.calculate_signal_strength(last_row)
            
            # Логирование текущих значений индикаторов
            logger.debug(f"\nDetailed analysis for {symbol}:")
            logger.debug(f"EMA5/EMA13 cross: {last_row['EMA5']} / {last_row['EMA13']}")
            logger.debug(f"RSI: {last_row['RSI']}")
            logger.debug(f"MACD/Signal: {last_row['MACD']} / {last_row['Signal_Line']}")
            logger.debug(f"Price vs BB_middle: {last_row['close']} / {last_row['BB_middle']}")
            logger.debug(f"Momentum: {last_row['Momentum']}")
            logger.debug(f"Signal Strength: {signal_strength}")

            # Условия для длинной позиции (LONG)
            long_conditions = [
                last_row['EMA5'] > last_row['EMA13'],
                last_row['RSI'] < 65,
                last_row['RSI'] > 30,
                last_row['MACD'] > last_row['Signal_Line'],
                last_row['close'] > last_row['BB_middle'],
                last_row['Momentum'] > 0,
                signal_strength >= self.trading_settings['min_signal_strength']
            ]
            
            # Условия для короткой позиции (SHORT)
            short_conditions = [
                last_row['EMA5'] < last_row['EMA13'],
                last_row['RSI'] > 35,
                last_row['RSI'] < 65,
                last_row['MACD'] < last_row['Signal_Line'],
                last_row['close'] < last_row['BB_middle'],
                last_row['Momentum'] < 0,
                signal_strength >= self.trading_settings['min_signal_strength']
            ]

            # Логирование условий
            logger.debug("\nLONG conditions check:")
            logger.debug(f"EMA cross: {long_conditions[0]}")
            logger.debug(f"RSI < 65: {long_conditions[1]}")
            logger.debug(f"RSI > 30: {long_conditions[2]}")
            logger.debug(f"MACD > Signal: {long_conditions[3]}")
            logger.debug(f"Price > BB_middle: {long_conditions[4]}")
            logger.debug(f"Momentum > 0: {long_conditions[5]}")
            logger.debug(f"Signal Strength >= {self.trading_settings['min_signal_strength']}: {long_conditions[6]}")

            logger.debug("\nSHORT conditions check:")
            logger.debug(f"EMA cross: {short_conditions[0]}")
            logger.debug(f"RSI > 35: {short_conditions[1]}")
            logger.debug(f"RSI < 65: {short_conditions[2]}")
            logger.debug(f"MACD < Signal: {short_conditions[3]}")
            logger.debug(f"Price < BB_middle: {short_conditions[4]}")
            logger.debug(f"Momentum < 0: {short_conditions[5]}")
            logger.debug(f"Signal Strength >= {self.trading_settings['min_signal_strength']}: {short_conditions[6]}")

            # Проверка условий и формирование сигналов
            if all(long_conditions):
                signal = {
                    'type': 'BUY',
                    'symbol': symbol,
                    'price': last_row['close'],
                    'signal_strength': signal_strength,
                    'stop_loss': last_row['close'] * 0.993,
                    'take_profit': last_row['close'] * 1.018
                }
                signals.append(signal)
                logger.info(f"Generated LONG signal for {symbol} with strength {signal_strength:.2f}%")

            elif all(short_conditions):
                signal = {
                    'type': 'SELL',
                    'symbol': symbol,
                    'price': last_row['close'],
                    'signal_strength': signal_strength,
                    'stop_loss': last_row['close'] * 1.007,
                    'take_profit': last_row['close'] * 0.982
                }
                signals.append(signal)
                logger.info(f"Generated SHORT signal for {symbol} with strength {signal_strength:.2f}%")

            return signals

        except Exception as e:
            logger.error(f"Error analyzing scalping signals: {str(e)}")
            logger.exception("Full traceback:")
            return []

    async def process_signals(self, signals: list, symbol: str):
        """
        Обработка торговых сигналов
        
        Args:
            signals (list): Список сигналов для обработки
            symbol (str): Торговая пара
        """
        try:
            for signal in signals:
                if not self.risk_manager.check_risk_limits(signal['price'], symbol):
                    logger.warning(f"Risk limits exceeded for {symbol}, skipping signal")
                    continue

                # Расчет размера позиции
                position_size = self.risk_manager.calculate_position_size(
                    signal['price'],
                    signal['stop_loss'],
                    self.current_balance
                )

                if position_size <= 0:
                    logger.warning(f"Invalid position size calculated for {symbol}")
                    continue

                # Размещение ордера
                    order = self.binance.place_order(
                        symbol=symbol,
                        side=signal['type'],
                        quantity=position_size,
                        stop_loss=signal['price'] * 0.993,  # 0.7% стоп-лосс (было 0.5%)
                        take_profit=signal['price'] * 1.018  # 1.8% тейк-профит (было 1.5%)
                    )

                if order:
                    # Сохранение информации о сделке
                    self.active_trades[symbol] = {
                        'type': signal['type'],
                        'entry_price': signal['price'],
                        'quantity': position_size,
                        'stop_loss': signal['stop_loss'],
                        'take_profit': signal['take_profit'],
                        'timestamp': datetime.now(),
                        'signal_strength': signal['signal_strength']
                    }

                    # Отправка уведомления
                    await self.telegram.send_trade_signal(
                        symbol=symbol,
                        signal_type=signal['type'],
                        entry_price=signal['price'],
                        stop_loss=signal['stop_loss'],
                        take_profit=signal['take_profit'],
                        signal_strength=signal['signal_strength']
                    )

                    logger.info(f"Processed {signal['type']} signal for {symbol}")

        except Exception as e:
            logger.error(f"Error processing signals: {str(e)}")
            logger.exception("Full traceback:")

    async def cleanup(self):
        """Очистка ресурсов перед завершением работы"""
        try:
            logger.info("Starting cleanup process...")
            
            # Установка флага завершения
            self.should_run = False

            # Закрытие всех активных позиций
            for symbol in list(self.active_trades.keys()):
                try:
                    trade = self.active_trades[symbol]
                    await self.binance.place_order(
                        symbol=symbol,
                        side='SELL' if trade['type'] == 'BUY' else 'BUY',
                        quantity=trade['quantity']
                    )
                    logger.info(f"Closed position for {symbol} during cleanup")
                except Exception as e:
                    logger.error(f"Error closing position for {symbol}: {str(e)}")

            # Безопасное закрытие WebSocket соединений
            for connection in list(self.ws_connections):
                try:
                    if hasattr(connection, 'close'):
                        await connection.close()
                    self.ws_connections.remove(connection)
                except Exception as e:
                    logger.error(f"Error closing WebSocket connection: {str(e)}")
            self.ws_connections.clear()

            # Закрытие основного WebSocket клиента
            if self.ws_client:
                try:
                    await self.ws_client.close_connection()
                    logger.info("WebSocket client closed")
                except Exception as e:
                    logger.error(f"Error closing WebSocket client: {str(e)}")

            # Отмена всех задач
            try:
                tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
                if tasks:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Error cancelling tasks: {str(e)}")

            logger.info("Cleanup completed successfully")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
        finally:
            # Останавливаем event loop
            try:
                if self.loop and self.loop.is_running():
                    self.loop.stop()
            except Exception as e:
                logger.error(f"Error stopping event loop: {str(e)}")

    def run(self):
        """Основной метод запуска бота"""
        try:
            # Создаём новый event loop для этого потока
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            async def main_loop():
                try:
                    # Инициализация WebSocket подключений
                    await self.init_websockets()

                    # Запуск веб-интерфейса
                    if os.getenv('WEB_INTERFACE_ENABLED', 'true').lower() == 'true':
                        web_thread = threading.Thread(target=start_web_server)
                        web_thread.daemon = True
                        web_thread.start()
                        logger.info("Web interface started")

                    # Обновление начального баланса
                    self.update_balance()

                    # Основной цикл работы бота
                    while self.should_run:
                        try:
                            self.manage_active_trades()
                            self.update_balance()
                            
                            if self.enable_predictions:
                                await self.generate_and_send_predictions()
                            
                            if os.getenv('WEB_INTERFACE_ENABLED', 'true').lower() != 'true':
                                self.display_console_info()
                            await asyncio.sleep(self.check_interval)
                        except Exception as e:
                            logger.error(f"Error in main loop iteration: {str(e)}")
                            await asyncio.sleep(60)

                except Exception as e:
                    logger.error(f"Error in async main loop: {str(e)}")
                    logger.exception("Full traceback:")

            def run_loop():
                try:
                    self.loop.run_until_complete(main_loop())
                except (KeyboardInterrupt, RuntimeError):
                    pass
                finally:
                    self.loop.run_until_complete(self.cleanup())
                    self.loop.close()

            # Запуск основного цикла в отдельном потоке
            self.main_task = threading.Thread(target=run_loop)
            self.main_task.start()

            # Ожидание завершения работы
            try:
                while self.main_task.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")
                self.should_run = False
                self.main_task.join(timeout=10)

        except Exception as e:
            logger.error(f"Error in bot run method: {str(e)}")
            logger.exception("Full traceback:")
            raise

if __name__ == "__main__":
    bot = TradingBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
        asyncio.run(bot.cleanup())
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        asyncio.run(bot.cleanup())