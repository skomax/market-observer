# создайте новый файл src/prediction_manager.py и вставьте в него этот код
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PredictionManager:
    def __init__(self):
        self.models = {}
        self.last_predictions = {}
        self.last_prediction_prices = {}
        self.pending_predictions = {}  # Для хранения активных прогнозов
        
    def store_prediction(self, symbol: str, prediction: dict):
        """Сохранение прогноза для последующей проверки"""
        try:
            if symbol not in self.pending_predictions:
                self.pending_predictions[symbol] = []
                
            # Сохраняем прогноз с временем проверки
            for timeframe, pred_data in prediction['predictions'].items():
                check_time = prediction['timestamp'] + timedelta(minutes=timeframe)
                self.pending_predictions[symbol].append({
                    'check_time': check_time,
                    'predicted_price': pred_data['price'],
                    'range_low': pred_data['range_low'],
                    'range_high': pred_data['range_high'],
                    'timeframe': timeframe,
                    'original_prediction': prediction
                })
                
            # Сортируем по времени проверки
            self.pending_predictions[symbol].sort(key=lambda x: x['check_time'])
            
        except Exception as e:
            logger.error(f"Error storing prediction: {str(e)}")
            
    def get_prediction_accuracy_message(self, prediction: dict, actual_price: float, timeframe: int) -> str:
        """Формирование сообщения о точности прогноза"""
        try:
            predicted_price = prediction['predicted_price']
            deviation = abs(actual_price - predicted_price)
            deviation_percent = (deviation / predicted_price) * 100
            
            within_range = prediction['range_low'] <= actual_price <= prediction['range_high']
            
            # Определение направления движения
            direction = "выше" if actual_price > predicted_price else "ниже"
            
            message = (
                f"📊 Проверка прогноза ({timeframe} мин)\n"
                f"Пара: {prediction['original_prediction']['symbol']}\n\n"
                f"🎯 Прогноз: {predicted_price:.8f}\n"
                f"📌 Факт: {actual_price:.8f}\n"
                f"📊 Отклонение: {deviation_percent:.2f}%\n"
                f"↕️ Направление: {direction} прогноза\n"
                f"📐 В диапазоне: {'✅' if within_range else '❌'}\n\n"
                f"Диапазон прогноза:\n"
                f"⬆️ Верхняя граница: {prediction['range_high']:.8f}\n"
                f"⬇️ Нижняя граница: {prediction['range_low']:.8f}\n"
            )
            
            # Добавляем оценку точности
            if deviation_percent < 1:
                message += "🎯 Очень точный прогноз!"
            elif deviation_percent < 2:
                message += "✅ Хороший прогноз"
            elif deviation_percent < 5:
                message += "📊 Приемлемая точность"
            else:
                message += "❌ Значительное отклонение"
                
            return message
            
        except Exception as e:
            logger.error(f"Error creating accuracy message: {str(e)}")
            return None
        
    def is_significant_change(self, symbol: str, current_price: float, min_change_percent: float) -> bool:
        """
        Проверяет, произошло ли существенное изменение цены с последнего прогноза
        """
        try:
            if symbol not in self.last_prediction_prices:
                self.last_prediction_prices[symbol] = current_price
                return True
                
            last_price = self.last_prediction_prices[symbol]
            price_change_percent = abs((current_price - last_price) / last_price * 100)
            
            if price_change_percent >= min_change_percent:
                self.last_prediction_prices[symbol] = current_price
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking significant change: {str(e)}")
            return False
        
    def calculate_trend_strength(self, prices):
        """Расчет силы тренда"""
        try:
            X = np.arange(len(prices)).reshape(-1, 1)
            y = np.array(prices)
            model = LinearRegression()
            model.fit(X, y)
            slope = model.coef_[0]
            r_squared = model.score(X, y)
            return slope, r_squared
        except Exception as e:
            logger.error(f"Error calculating trend strength: {str(e)}")
            return 0, 0

    def get_prediction(self, symbol: str, price_data: list, timeframes: list = [5, 15]):
        """Генерация прогноза для символа"""
        try:
            if len(price_data) < 30:
                return None

            prices = [float(p['close']) for p in price_data[-30:]]
            current_price = prices[-1]
            
            # Расчет тренда
            slope, r_squared = self.calculate_trend_strength(prices)
            
            # Определение тренда
            if abs(slope) < 0.0001:
                trend = "Боковой"
            elif slope > 0:
                trend = "Восходящий"
            else:
                trend = "Нисходящий"

            # Расчет волатильности
            volatility = np.std(prices) / np.mean(prices) * 100

            # Прогнозы для разных временных промежутков
            predictions = {}
            for tf in timeframes:
                future_price = current_price + (slope * tf)
                range_width = (volatility * current_price) / 100
                predictions[tf] = {
                    'price': future_price,
                    'range_low': future_price - range_width,
                    'range_high': future_price + range_width
                }

            return {
                'symbol': symbol,
                'current_price': current_price,
                'trend': trend,
                'trend_strength': abs(r_squared * 100),
                'volatility': volatility,
                'predictions': predictions,
                'timestamp': datetime.now()
            }

        except Exception as e:
            logger.error(f"Error generating prediction for {symbol}: {str(e)}")
            return None

    def format_prediction_message(self, prediction):
        """Форматирование прогноза для отправки в Telegram"""
        try:
            if not prediction:
                return None

            next_prediction_time = prediction['timestamp'] + timedelta(minutes=15)  # или другой интервал
            
            message = (
                f"📊 Прогноз для {prediction['symbol']}\n\n"
                f"⏰ Время прогноза: {prediction['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"⏳ Следующий прогноз после: {next_prediction_time.strftime('%H:%M:%S')}\n\n"
                f"💵 Текущая цена: {prediction['current_price']:.8f}\n"
                f"📈 Тренд: {prediction['trend']}\n"
                f"💪 Сила тренда: {prediction['trend_strength']:.1f}%\n"
                f"📊 Волатильность: {prediction['volatility']:.1f}%\n\n"
                f"🔮 Прогноз:\n"
            )

            for tf, pred in prediction['predictions'].items():
                message += (
                    f"\n{tf} минут:\n"
                    f"Ожидаемая цена: {pred['price']:.8f}\n"
                    f"Диапазон: {pred['range_low']:.8f} - {pred['range_high']:.8f}\n"
                )

            return message

        except Exception as e:
            logger.error(f"Error formatting prediction message: {str(e)}")
            return None

    def analyze_prediction_accuracy(self, symbol: str, prediction_data: dict, actual_price: float):
        """Анализ точности прогноза"""
        try:
            predicted_price = prediction_data['predictions'][15]['price']
            error_percent = abs(actual_price - predicted_price) / predicted_price * 100
            
            accuracy = 100 - error_percent
            
            within_range = (
                prediction_data['predictions'][15]['range_low'] <= actual_price <= 
                prediction_data['predictions'][15]['range_high']
            )
            
            return {
                'accuracy': accuracy,
                'within_range': within_range,
                'error_percent': error_percent
            }
            
        except Exception as e:
            logger.error(f"Error analyzing prediction accuracy: {str(e)}")
            return None