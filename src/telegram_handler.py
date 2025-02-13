import telegram
from telegram.ext import Updater
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelegramHandler:
    def __init__(self, token: str, channel_id: str):
        """Инициализация обработчика Telegram"""
        try:
            self.bot = telegram.Bot(token=token)
            self.channel_id = channel_id
            self.updater = Updater(token=token, use_context=True)
            
            # Проверка подключения
            self.bot.get_me()
            logger.info(f"Telegram handler initialized for channel: {channel_id}")
            
            # Отправка тестового сообщения при инициализации
            self.send_message("🤖 Telegram connection established")
            
        except Exception as e:
            logger.error(f"Error initializing Telegram handler: {str(e)}")
            raise

    def send_message(self, message: str) -> bool:
        """Базовый метод отправки сообщения"""
        try:
            self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode=telegram.ParseMode.HTML
            )
            return True
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    def send_custom_message(self, message: str, message_type: str = "INFO") -> bool:
        """Отправка пользовательского сообщения"""
        try:
            logger.info(f"Sending {message_type} message to channel {self.channel_id}")
            return self.send_message(message)
        except Exception as e:
            logger.error(f"Error sending custom message: {str(e)}")
            return False

    def send_analysis_update(self, symbol: str, data: Dict[str, Any]) -> bool:
        """Отправка обновления анализа"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Определение тренда
            trend = "UPTREND" if data['ema5'] > data['ema13'] else "DOWNTREND"
            
            # Расчет процентных расстояний
            ema5_distance = ((data['current_price'] - data['ema5']) / data['ema5']) * 100
            ema13_distance = ((data['current_price'] - data['ema13']) / data['ema13']) * 100
            
            # Определение рекомендации
            if data.get('signal_strength', 0) >= 70:
                recommendation = "🟢 STRONG BUY"
            elif data.get('signal_strength', 0) >= 50:
                recommendation = "🟡 CONSIDER BUY"
            elif data.get('signal_strength', 0) <= 30:
                recommendation = "🔴 CONSIDER SELL"
            else:
                recommendation = "⚪️ NEUTRAL"

            # Формирование сообщения
            message = (
                f"📊 Scalping Analysis Update\n\n"
                f"Symbol: {symbol}\n"
                f"Current Price: {data['current_price']:.8f}\n\n"
                f"Technical Indicators:\n"
                f"• EMA5: {data['ema5']:.8f} ({ema5_distance:+.2f}%)\n"
                f"• EMA13: {data['ema13']:.8f} ({ema13_distance:+.2f}%)\n"
                f"• RSI: {data['rsi']:.2f}\n"
                f"• MACD: {data['macd']:.8f}\n"
                f"• Signal Line: {data['signal_line']:.8f}\n\n"
                f"Analysis:\n"
                f"• Trend: {trend}\n"
                f"• Signal Strength: {data.get('signal_strength', 0):.1f}%\n"
                f"• Recommendation: {recommendation}\n\n"
                f"Time: {timestamp}"
            )
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending analysis update: {str(e)}")
            return False

    def send_signal(self, symbol: str, signal_type: str, price: float, analysis_info: str) -> bool:
        """Отправка торгового сигнала"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            signal_emoji = "🟢" if signal_type == "BUY" else "🔴"
            
            message = (
                f"{signal_emoji} SCALPING SIGNAL\n\n"
                f"Symbol: {symbol}\n"
                f"Action: {signal_type}\n"
                f"Price: {price:.8f}\n\n"
                f"{analysis_info}\n\n"
                f"Time: {timestamp}"
            )
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending signal: {str(e)}")
            return False

    def send_trade_result(self, symbol: str, entry_price: float, 
                         exit_price: float, profit_loss: float, duration: str) -> bool:
        """Отправка результата сделки"""
        try:
            profit_percent = (profit_loss / (entry_price)) * 100
            
            # Определение статуса сделки
            if profit_percent > 2:
                result_emoji = "🟢🟢"
                status = "EXCELLENT"
            elif profit_percent > 0:
                result_emoji = "🟢"
                status = "PROFITABLE"
            elif profit_percent > -1:
                result_emoji = "🟡"
                status = "SMALL LOSS"
            else:
                result_emoji = "🔴"
                status = "LOSS"
            
            # Расчет часовой доходности
            try:
                duration_minutes = float(duration.split(':')[1])
                hourly_return = profit_percent * (60 / duration_minutes)
            except:
                hourly_return = 0
            
            message = (
                f"📊 Trade Result {result_emoji}\n\n"
                f"Symbol: {symbol}\n"
                f"Status: {status}\n\n"
                f"Trade Details:\n"
                f"• Entry Price: {entry_price:.8f}\n"
                f"• Exit Price: {exit_price:.8f}\n"
                f"• P/L: {profit_loss:.8f} ({profit_percent:+.2f}%)\n"
                f"• Duration: {duration}\n\n"
                f"Performance Metrics:\n"
                f"• Hourly Return: {hourly_return:.2f}%\n"
                f"• Price Movement: {((exit_price - entry_price)/entry_price)*100:+.2f}%\n"
                f"• Execution Quality: {abs(profit_percent/((exit_price - entry_price)/entry_price)*100):.0f}%\n\n"
                f"🎯 Trade Rating: {'⭐'* (int(min(5, max(1, profit_percent + 3))))}"
            )
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending trade result: {str(e)}")
            return False

    def send_daily_summary(self, total_trades: int, successful_trades: int, 
                          total_profit_loss: float, win_rate: float) -> bool:
        """Отправка ежедневной сводки"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d")
            
            # Определение статуса дня
            if win_rate >= 70:
                status_emoji = "🟢🟢"
                status = "EXCELLENT"
            elif win_rate >= 50:
                status_emoji = "🟢"
                status = "GOOD"
            elif win_rate >= 40:
                status_emoji = "🟡"
                status = "MODERATE"
            else:
                status_emoji = "🔴"
                status = "POOR"
            
            message = (
                f"📈 Daily Trading Summary {status_emoji}\n"
                f"Date: {timestamp}\n"
                f"Status: {status}\n\n"
                f"Performance Metrics:\n"
                f"• Total Trades: {total_trades}\n"
                f"• Successful Trades: {successful_trades}\n"
                f"• Win Rate: {win_rate:.2f}%\n"
                f"• Total P/L: {total_profit_loss:.8f} USDT\n\n"
                f"Average Metrics:\n"
                f"• Avg. Profit per Trade: {total_profit_loss/total_trades:.8f} USDT\n"
                f"• Avg. Win Rate: {win_rate:.2f}%\n"
                f"• Success Ratio: {successful_trades}/{total_trades}\n\n"
                f"Rating: {'⭐'* (int(min(5, max(1, win_rate/20))))}"\
                f"\n\nNext day target: {abs(total_profit_loss) * 1.2:.8f} USDT"
            )
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending daily summary: {str(e)}")
            return False

    def send_error(self, error_message: str, error_type: Optional[str] = None) -> bool:
        """Отправка уведомления об ошибке"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            message = (
                f"⚠️ ERROR ALERT\n\n"
                f"Time: {timestamp}\n"
                f"Type: {error_type if error_type else 'General Error'}\n"
                f"Message: {error_message}\n\n"
                f"Please check the logs for more details."
            )
            
            return self.send_message(message)
            
        except Exception as e:
            logger.error(f"Error sending error alert: {str(e)}")
            return False
