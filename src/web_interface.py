from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import os
from datetime import datetime
import socket
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def find_free_port(start_port=3000, max_port=3010):
    """Поиск свободного порта"""
    for port in range(start_port, max_port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', port))
            sock.close()
            return port
        except OSError:
            sock.close()
            continue
    raise OSError(f"No free ports found in range {start_port}-{max_port}")

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    if username == os.getenv('WEB_USERNAME'):
        return User(username)
    return None

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/api/dashboard-data')
@login_required
def dashboard_data():
    from src.main import TradingBot
    bot = TradingBot()
    data = {
        'starting_balance': bot.starting_balance,
        'current_balance': bot.current_balance,
        'profit_loss': bot.current_balance - bot.starting_balance if bot.starting_balance else 0,
        'active_trades': bot.get_active_trades() if hasattr(bot, 'get_active_trades') else [],
        'recent_signals': bot.get_recent_signals() if hasattr(bot, 'get_recent_signals') else []
    }
    return jsonify(data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if (username == os.getenv('WEB_USERNAME') and 
            password == os.getenv('WEB_PASSWORD')):
            login_user(User(username))
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def start_web_server():
    """Запуск веб-сервера с автоматическим поиском свободного порта"""
    try:
        port = find_free_port()
        print(f"Starting web server on port {port}")
        app.run(host='0.0.0.0', port=port, use_reloader=False)
    except Exception as e:
        logger.error(f"Error starting web server: {str(e)}")
