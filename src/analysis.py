import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalysis:
    def __init__(self):
        self.signals = []

    def calculate_indicators(self, df):
        """Расчет технических индикаторов"""
        try:
            # Рассчитываем EMA
            df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
            
            # Рассчитываем RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Рассчитываем MACD
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
            
            # Bollinger Bands
            df['BB_middle'] = df['close'].rolling(window=20).mean()
            df['BB_upper'] = df['BB_middle'] + 2 * df['close'].rolling(window=20).std()
            df['BB_lower'] = df['BB_middle'] - 2 * df['close'].rolling(window=20).std()
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def generate_signals(self, df):
        """Генерация торговых сигналов на основе технических индикаторов"""
        try:
            signals = []
            
            for i in range(len(df)-1):
                # Проверяем пересечение EMA
                ema_cross_up = (df['EMA20'].iloc[i] > df['EMA50'].iloc[i] and 
                              df['EMA20'].iloc[i-1] <= df['EMA50'].iloc[i-1])
                
                ema_cross_down = (df['EMA20'].iloc[i] < df['EMA50'].iloc[i] and 
                                df['EMA20'].iloc[i-1] >= df['EMA50'].iloc[i-1])
                
                # Проверяем RSI
                rsi_oversold = df['RSI'].iloc[i] < 30
                rsi_overbought = df['RSI'].iloc[i] > 70
                
                # Проверяем MACD
                macd_cross_up = (df['MACD'].iloc[i] > df['Signal_Line'].iloc[i] and 
                               df['MACD'].iloc[i-1] <= df['Signal_Line'].iloc[i-1])
                
                macd_cross_down = (df['MACD'].iloc[i] < df['Signal_Line'].iloc[i] and 
                                 df['MACD'].iloc[i-1] >= df['Signal_Line'].iloc[i-1])
                
                # Генерация сигналов
                if (ema_cross_up and rsi_oversold) or macd_cross_up:
                    signals.append({
                        'timestamp': df.index[i],
                        'type': 'BUY',
                        'price': df['close'].iloc[i],
                        'strength': self.calculate_signal_strength(df, i, 'BUY')
                    })
                
                elif (ema_cross_down and rsi_overbought) or macd_cross_down:
                    signals.append({
                        'timestamp': df.index[i],
                        'type': 'SELL',
                        'price': df['close'].iloc[i],
                        'strength': self.calculate_signal_strength(df, i, 'SELL')
                    })
            
            return signals
            
        except Exception as e:
            logger.error(f"Error generating signals: {str(e)}")
            return []

    def calculate_signal_strength(self, df, index, signal_type):
        """Расчет силы сигнала на основе множества факторов"""
        strength = 0
        
        try:
            # RSI factor
            rsi = df['RSI'].iloc[index]
            if signal_type == 'BUY':
                strength += (70 - rsi) / 30
            else:
                strength += (rsi - 30) / 30
            
            # Bollinger Bands factor
            price = df['close'].iloc[index]
            bb_upper = df['BB_upper'].iloc[index]
            bb_lower = df['BB_lower'].iloc[index]
            
            if signal_type == 'BUY' and price <= bb_lower:
                strength += 1
            elif signal_type == 'SELL' and price >= bb_upper:
                strength += 1
            
            # Volume factor
            avg_volume = df['volume'].rolling(window=20).mean().iloc[index]
            current_volume = df['volume'].iloc[index]
            volume_factor = current_volume / avg_volume
            strength += min(volume_factor - 1, 1)
            
            # Normalize strength to 0-1 range
            strength = min(max(strength / 3, 0), 1)
            
            return strength
            
        except Exception as e:
            logger.error(f"Error calculating signal strength: {str(e)}")
            return 0.5

    def validate_signal(self, signal, historical_data):
        """Проверка сигнала на ложные срабатывания"""
        try:
            # Получаем последние данные
            recent_data = historical_data.tail(10)
            
            # Проверяем волатильность
            volatility = recent_data['close'].std() / recent_data['close'].mean()
            if volatility > 0.1:  # Высокая волатильность
                return False
            
            # Проверяем объем
            avg_volume = historical_data['volume'].mean()
            current_volume = historical_data['volume'].iloc[-1]
            if current_volume < avg_volume * 0.5:  # Низкий объем
                return False
            
            # Дополнительные проверки можно добавить здесь
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating signal: {str(e)}")
            return False
