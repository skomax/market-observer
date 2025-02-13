import logging
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        # Загрузка переменных окружения
        load_dotenv()
        
        # Параметры размера позиции
        self.max_position_size = float(os.getenv('MAX_POSITION_SIZE', 0.1))
        self.min_position_size = float(os.getenv('MIN_POSITION_SIZE', 0.01))
        self.default_position_size = float(os.getenv('DEFAULT_POSITION_SIZE', 0.05))
        self.fixed_lot_size = float(os.getenv('FIXED_LOT_SIZE', 100))
        self.use_fixed_lot = os.getenv('USE_FIXED_LOT', 'false').lower() == 'true'
        
        # Параметры управления рисками
        self.max_daily_loss = float(os.getenv('MAX_DAILY_LOSS', 0.05))  # 5% от баланса
        self.max_position_loss = float(os.getenv('MAX_POSITION_LOSS', 0.02))  # 2% на позицию
        
        # Статистика торговли
        self.daily_stats = {
            'date': datetime.now().date(),
            'trades': 0,
            'profit_loss': 0,
            'winning_trades': 0,
            'losing_trades': 0
        }
        
        # История торговли
        self.trade_history = []
        
    def check_risk_limits(self, price, symbol):
        """
        Проверка лимитов риска для новой позиции
        
        Args:
            price (float): Цена входа
            symbol (str): Торговая пара
            
        Returns:
            bool: True если риски в допустимых пределах, False если нет
        """
        try:
            current_date = datetime.now().date()
            
            # Проверяем, не превышен ли дневной лимит убытков
            if abs(self.daily_stats['profit_loss']) >= self.max_daily_loss:
                logger.warning(f"Daily loss limit reached for {symbol}")
                return False
                
            # Проверяем количество открытых позиций
            open_positions = len([t for t in self.trade_history if not t.get('exit_time')])
            max_positions = int(os.getenv('MAX_OPEN_POSITIONS', 3))
            if open_positions >= max_positions:
                logger.warning(f"Maximum number of positions ({max_positions}) reached")
                return False
                
            # Проверяем время последней сделки
            min_time_between_trades = int(os.getenv('MIN_TIME_BETWEEN_TRADES', 300))  # 5 минут по умолчанию
            if self.trade_history:
                last_trade_time = self.trade_history[-1]['timestamp']
                time_since_last_trade = (datetime.now() - last_trade_time).total_seconds()
                if time_since_last_trade < min_time_between_trades:
                    logger.warning(f"Minimum time between trades not reached for {symbol}")
                    return False
                    
            # Проверяем максимальный риск на позицию
            position_value = price
            account_balance = float(os.getenv('INITIAL_BALANCE', 1000))  # Нужно передавать актуальный баланс
            max_position_value = account_balance * self.max_position_size
            
            if position_value > max_position_value:
                logger.warning(f"Position size exceeds maximum allowed for {symbol}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error checking risk limits: {str(e)}")
            return False

    def calculate_lot_size(self, account_balance, current_price):
        """Расчет размера лота"""
        try:
            if self.use_fixed_lot:
                return self.fixed_lot_size / current_price
            
            # Расчет на основе процента от баланса
            position_value = account_balance * self.default_position_size
            
            # Проверка ограничений
            if position_value > account_balance * self.max_position_size:
                position_value = account_balance * self.max_position_size
            elif position_value < account_balance * self.min_position_size:
                position_value = account_balance * self.min_position_size
            
            return position_value / current_price
        
        except Exception as e:
            logger.error(f"Error calculating lot size: {str(e)}")
            return 0

    def check_trade_allowed(self, account_balance, symbol):
        """Проверка возможности совершения сделки"""
        try:
            current_date = datetime.now().date()
            
            # Сброс статистики при новом дне
            if current_date != self.daily_stats['date']:
                self.daily_stats = {
                    'date': current_date,
                    'trades': 0,
                    'profit_loss': 0,
                    'winning_trades': 0,
                    'losing_trades': 0
                }
            
            # Проверка дневного убытка
            if abs(self.daily_stats['profit_loss']) > (account_balance * self.max_daily_loss):
                logger.warning(f"Daily loss limit reached for {symbol}")
                return False
            
            # Проверка количества открытых позиций
            max_positions = int(os.getenv('MAX_OPEN_POSITIONS', 3))
            if len([t for t in self.trade_history if not t.get('exit_time')]) >= max_positions:
                logger.warning(f"Maximum number of positions reached")
                return False
            
            # Дополнительные проверки можно добавить здесь
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking trade allowance: {str(e)}")
            return False

    def calculate_stop_loss(self, entry_price, side, volatility=None):
        """Расчет уровня stop-loss"""
        try:
            # Получаем процент стоп-лосса из конфигурации или используем значение по умолчанию
            stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', 0.02))
            
            # Корректировка на основе волатильности, если она предоставлена
            if volatility:
                # Увеличиваем стоп-лосс при высокой волатильности
                volatility_adjustment = min(volatility * 2, 0.02)
                stop_loss_percent += volatility_adjustment
            
            if side.upper() == 'BUY':
                stop_loss = entry_price * (1 - stop_loss_percent)
            else:
                stop_loss = entry_price * (1 + stop_loss_percent)
            
            return stop_loss
            
        except Exception as e:
            logger.error(f"Error calculating stop loss: {str(e)}")
            return None

    def calculate_take_profit(self, entry_price, side, risk_reward_ratio=None):
        """Расчет уровня take-profit"""
        try:
            # Если соотношение риск/прибыль не указано, берем из конфигурации
            if risk_reward_ratio is None:
                risk_reward_ratio = float(os.getenv('RISK_REWARD_RATIO', 2.0))
            
            # Получаем процент стоп-лосса
            stop_loss_percent = float(os.getenv('STOP_LOSS_PERCENT', 0.02))
            
            # Рассчитываем тейк-профит на основе риск/прибыль
            take_profit_percent = stop_loss_percent * risk_reward_ratio
            
            if side.upper() == 'BUY':
                take_profit = entry_price * (1 + take_profit_percent)
            else:
                take_profit = entry_price * (1 - take_profit_percent)
            
            return take_profit
            
        except Exception as e:
            logger.error(f"Error calculating take profit: {str(e)}")
            return None

    def update_trade_stats(self, profit_loss, trade_result):
        """Обновление торговой статистики"""
        try:
            current_date = datetime.now().date()
            
            # Сброс статистики при новом дне
            if current_date != self.daily_stats['date']:
                self.daily_stats = {
                    'date': current_date,
                    'trades': 0,
                    'profit_loss': 0,
                    'winning_trades': 0,
                    'losing_trades': 0
                }
            
            self.daily_stats['trades'] += 1
            self.daily_stats['profit_loss'] += profit_loss
            
            if profit_loss > 0:
                self.daily_stats['winning_trades'] += 1
            else:
                self.daily_stats['losing_trades'] += 1
            
            # Добавление сделки в историю
            trade_record = {
                'timestamp': datetime.now(),
                'profit_loss': profit_loss,
                'result': trade_result
            }
            self.trade_history.append(trade_record)
            
            # Ограничение размера истории
            max_history = int(os.getenv('MAX_TRADE_HISTORY', 1000))
            if len(self.trade_history) > max_history:
                self.trade_history = self.trade_history[-max_history:]
            
        except Exception as e:
            logger.error(f"Error updating trade stats: {str(e)}")

    def get_trading_stats(self):
        """Получение статистики торговли"""
        try:
            stats = {
                'daily_stats': self.daily_stats.copy(),
                'win_rate': (self.daily_stats['winning_trades'] / self.daily_stats['trades'] * 100 
                           if self.daily_stats['trades'] > 0 else 0),
                'total_trades': self.daily_stats['trades'],
                'total_profit_loss': self.daily_stats['profit_loss']
            }
            return stats
            
        except Exception as e:
            logger.error(f"Error getting trading stats: {str(e)}")
            return None
            
    def get_stats(self):
        """Получение статистики для отображения"""
        try:
            # Расчет общей статистики
            total_trades = len(self.trade_history)
            if total_trades == 0:
                return {
                    'win_rate': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'total_trades': 0,
                    'profit_loss': 0
                }

            winning_trades = [t for t in self.trade_history if t['profit_loss'] > 0]
            losing_trades = [t for t in self.trade_history if t['profit_loss'] <= 0]

            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
            avg_win = sum([t['profit_loss'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
            avg_loss = sum([t['profit_loss'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
            total_profit_loss = sum([t['profit_loss'] for t in self.trade_history])

            return {
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'total_trades': total_trades,
                'profit_loss': total_profit_loss
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'total_trades': 0,
                'profit_loss': 0
            }

    def adjust_position_size(self, base_size, recent_performance):
        """Корректировка размера позиции на основе недавней производительности"""
        try:
            # Если недавняя производительность хорошая, можно увеличить размер
            if recent_performance > 0.6:  # Выигрышных более 60%
                return base_size * 1.2
            # Если плохая - уменьшить
            elif recent_performance < 0.4:  # Выигрышных менее 40%
                return base_size * 0.8
            return base_size
            
        except Exception as e:
            logger.error(f"Error adjusting position size: {str(e)}")
            return base_size

    def calculate_position_risk(self, position_size, current_price, stop_loss):
        """Расчет риска для позиции"""
        try:
            risk_amount = abs(current_price - stop_loss) * position_size
            return risk_amount
            
        except Exception as e:
            logger.error(f"Error calculating position risk: {str(e)}")
            return 0
