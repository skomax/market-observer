from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
Base = declarative_base()

class Signal(Base):
    __tablename__ = 'signals'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    signal_type = Column(String(20))
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    executed = Column(Boolean, default=False)
    success = Column(Boolean, default=None)
    profit_loss = Column(Float, default=None)

class Trade(Base):
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    entry_price = Column(Float)
    exit_price = Column(Float)
    quantity = Column(Float)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    profit_loss = Column(Float)
    success = Column(Boolean)
    
class PredictionAccuracy(Base):
    __tablename__ = 'prediction_accuracy'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    predicted_price = Column(Float)
    actual_price = Column(Float)
    deviation_percent = Column(Float)
    timeframe = Column(Integer)
    check_time = Column(DateTime)
    within_range = Column(Boolean)

class Prediction(Base):
    __tablename__ = 'predictions'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50))
    current_price = Column(Float)
    trend = Column(String(20))
    trend_strength = Column(Float)
    volatility = Column(Float)
    prediction_5min = Column(Float)
    prediction_15min = Column(Float)
    timestamp = Column(DateTime)

class DatabaseHandler:
    def __init__(self):
        db_url = (f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
                 f"@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}")
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def save_signal(self, symbol, signal_type, price):
        try:
            signal = Signal(
                symbol=symbol,
                signal_type=signal_type,
                price=price
            )
            self.session.add(signal)
            self.session.commit()
            return signal.id
        except Exception as e:
            logger.error(f"Error saving signal: {str(e)}")
            self.session.rollback()
            return None

    def save_prediction_accuracy(self, accuracy_data: dict):
        """Сохранение данных о точности прогноза"""
        try:
            accuracy = PredictionAccuracy(
                symbol=accuracy_data['symbol'],
                predicted_price=accuracy_data['predicted_price'],
                actual_price=accuracy_data['actual_price'],
                deviation_percent=accuracy_data['deviation_percent'],
                timeframe=accuracy_data['timeframe'],
                check_time=accuracy_data['check_time'],
                within_range=accuracy_data['within_range']
            )
            self.session.add(accuracy)
            self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving prediction accuracy: {str(e)}")
            self.session.rollback()
            return False

    def save_prediction(self, prediction: dict):
        """Сохранение прогноза в базу данных"""
        try:
            pred = Prediction(
                symbol=prediction['symbol'],
                current_price=prediction['current_price'],
                trend=prediction['trend'],
                trend_strength=prediction['trend_strength'],
                volatility=prediction['volatility'],
                prediction_5min=prediction['predictions'][5]['price'],
                prediction_15min=prediction['predictions'][15]['price'],
                timestamp=prediction['timestamp']
            )
            self.session.add(pred)
            self.session.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving prediction to database: {str(e)}")
            self.session.rollback()
            return False

    def save_trade(self, symbol, entry_price, exit_price, quantity, 
                  entry_time, exit_time, profit_loss):
        try:
            trade = Trade(
                symbol=symbol,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                entry_time=entry_time,
                exit_time=exit_time,
                profit_loss=profit_loss,
                success=(profit_loss > 0)
            )
            self.session.add(trade)
            self.session.commit()
            return trade.id
        except Exception as e:
            logger.error(f"Error saving trade: {str(e)}")
            self.session.rollback()
            return None

    def get_recent_signals(self, limit=10):
        return self.session.query(Signal)\
            .order_by(Signal.timestamp.desc())\
            .limit(limit)\
            .all()

    def get_recent_trades(self, limit=10):
        return self.session.query(Trade)\
            .order_by(Trade.exit_time.desc())\
            .limit(limit)\
            .all()

    def update_signal_status(self, signal_id, executed=True, success=None, profit_loss=None):
        try:
            signal = self.session.query(Signal).get(signal_id)
            if signal:
                signal.executed = executed
                signal.success = success
                signal.profit_loss = profit_loss
                self.session.commit()
        except Exception as e:
            logger.error(f"Error updating signal status: {str(e)}")
            self.session.rollback()