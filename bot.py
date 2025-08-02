import os
import logging
import sqlite3
import requests
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Состояния игры
GAME_STATES = {
    'WAITING_MODE': 'waiting_mode',
    'SINGLE_PLAYER': 'single_player',
    'GROUP_BATTLE': 'group_battle',
    'BATTLE_ACTIVE': 'battle_active'
}

def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            current_state TEXT DEFAULT 'waiting_mode',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица игр
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            game_type TEXT,
            movies_list TEXT,
            current_round INTEGER DEFAULT 1,
            total_rounds INTEGER,
            current_pair TEXT,
            votes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_user_state(user_id: int, state: str):
    """Сохранение состояния пользователя"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, current_state) 
        VALUES (?, ?)
    ''', (user_id, state))
    conn.commit()
    conn.close()

def get_user_state(user_id: int):
    """Получение состояния пользователя"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT current_state FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'waiting_mode'

def create_game(user_id: int, chat_id: int, game_type: str, movies_list: list):
    """Создание новой игры"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Сохраняем список фильмов как JSON строку
    import json
    movies_json = json.dumps(movies_list)
    total_rounds = len(movies_list) - 1  # Количество раундов до победителя
    
    cursor.execute('''
        INSERT INTO games (user_id, chat_id, game_type, movies_list, total_rounds)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, chat_id, game_type, movies_json, total_rounds))
    
    game_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return game_id

def get_current_game(user_id: int, chat_id: int):
    """Получение текущей игры"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM games 
        WHERE user_id = ? AND chat_id = ? 
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id, chat_id))
    result = cursor.fetchone()
    conn.close()
    return result

def update_game_round(game_id: int, current_round: int, current_pair: str, votes: str = None):
    """Обновление раунда игры"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    if votes:
        cursor.execute('''
            UPDATE games 
            SET current_round = ?, current_pair = ?, votes = ?
            WHERE game_id = ?
        ''', (current_round, current_pair, votes, game_id))
    else:
        cursor.execute('''
            UPDATE games 
            SET current_round = ?, current_pair = ?
            WHERE game_id = ?
        ''', (current_round, current_pair, game_id))
    
    conn.commit()
    conn.close()

def increment_game_round(game_id: int):
    """Увеличение номера раунда"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE games 
        SET current_round = current_round + 1
        WHERE game_id = ?
    ''', (game_id,))
    
    conn.commit()
    conn.close()

def get_popular_movies(count: int = 26):
    """Получение популярных фильмов для битвы"""
    try:
        # Проверяем, есть ли валидный API ключ
        if TMDB_API_KEY and TMDB_API_KEY != "placeholder_until_domain_ready":
            url = f"{TMDB_BASE_URL}/movie/popular"
            params = {
                'api_key': TMDB_API_KEY,
                'language': 'ru-RU',
                'page': 1,
                'include_adult': False
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            movies = data.get('results', [])
            
            # Перемешиваем и берем нужное количество
            random.shuffle(movies)
            return movies[:count]
        else:
            # Возвращаем заглушки фильмов
            return get_mock_popular_movies(count)
        
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к TMDb API: {e}")
        # Возвращаем заглушки при ошибке API
        return get_mock_popular_movies(count)

def get_mock_popular_movies(count: int = 26):
    """Заглушки популярных фильмов для работы без TMDb API"""
    mock_movies = [
        {
            'id': 1,
            'title': 'Побег из Шоушенка',
            'overview': 'История о надежде и дружбе в тюрьме Шоушенк.',
            'poster_path': None
        },
        {
            'id': 2,
            'title': 'Крёстный отец',
            'overview': 'Эпическая сага о семье Корлеоне.',
            'poster_path': None
        },
        {
            'id': 3,
            'title': 'Форрест Гамп',
            'overview': 'История простого человека с добрым сердцем.',
            'poster_path': None
        },
        {
            'id': 4,
            'title': 'Матрица',
            'overview': 'Мир, в котором человечество порабощено машинами.',
            'poster_path': None
        },
        {
            'id': 5,
            'title': 'Интерстеллар',
            'overview': 'Группа исследователей отправляется через червоточину.',
            'poster_path': None
        },
        {
            'id': 6,
            'title': 'Терминатор 2',
            'overview': 'Кибернетический организм из будущего.',
            'poster_path': None
        },
        {
            'id': 7,
            'title': 'Джокер',
            'overview': 'История становления одного из самых известных злодеев.',
            'poster_path': None
        },
        {
            'id': 8,
            'title': 'Бегущий по лезвию',
            'overview': 'Детектив в футуристическом Лос-Анджелесе.',
            'poster_path': None
        },
        {
            'id': 9,
            'title': 'Мальчишник в Вегасе',
            'overview': 'Четверо друзей отправляются в Лас-Вегас.',
            'poster_path': None
        },
        {
            'id': 10,
            'title': 'Мертвые поэты',
            'overview': 'История о группе студентов и их учителе.',
            'poster_path': None
        },
        {
            'id': 11,
            'title': 'Мадагаскар',
            'overview': 'Четыре животных из зоопарка на острове.',
            'poster_path': None
        },
        {
            'id': 12,
            'title': 'Миссия невыполнима',
            'overview': 'Агент Итан Хант должен доказать свою невиновность.',
            'poster_path': None
        },
        {
            'id': 13,
            'title': 'Титаник',
            'overview': 'История любви на фоне крушения корабля.',
            'poster_path': None
        },
        {
            'id': 14,
            'title': 'Аватар',
            'overview': 'История о планете Пандора и её обитателях.',
            'poster_path': None
        },
        {
            'id': 15,
            'title': 'Властелин колец',
            'overview': 'Эпическое путешествие по Средиземью.',
            'poster_path': None
        },
        {
            'id': 16,
            'title': 'Звездные войны',
            'overview': 'Эпическая сага о борьбе добра и зла.',
            'poster_path': None
        },
        {
            'id': 17,
            'title': 'Пираты Карибского моря',
            'overview': 'Приключения капитана Джека Воробья.',
            'poster_path': None
        },
        {
            'id': 18,
            'title': 'Гарри Поттер',
            'overview': 'История юного волшебника и его друзей.',
            'poster_path': None
        },
        {
            'id': 19,
            'title': 'Мстители',
            'overview': 'Команда супергероев спасает мир.',
            'poster_path': None
        },
        {
            'id': 20,
            'title': 'Темный рыцарь',
            'overview': 'Бэтмен противостоит Джокеру.',
            'poster_path': None
        },
        {
            'id': 21,
            'title': 'Начало',
            'overview': 'Фильм о сновидениях и реальности.',
            'poster_path': None
        },
        {
            'id': 22,
            'title': 'Криминальное чтиво',
            'overview': 'История преступного мира Лос-Анджелеса.',
            'poster_path': None
        },
        {
            'id': 23,
            'title': 'Список Шиндлера',
            'overview': 'История о спасении евреев во время Холокоста.',
            'poster_path': None
        },
        {
            'id': 24,
            'title': 'Красавица и чудовище',
            'overview': 'Сказка о любви и красоте души.',
            'poster_path': None
        },
        {
            'id': 25,
            'title': 'Король Лев',
            'overview': 'История о взрослении и ответственности.',
            'poster_path': None
        },
        {
            'id': 26,
            'title': 'Аладдин',
            'overview': 'Приключения уличного вора и джинна.',
            'poster_path': None
        }
    ]
    
    # Перемешиваем и берем нужное количество
    random.shuffle(mock_movies)
    return mock_movies[:count]

def format_movie_battle(movie1: dict, movie2: dict, round_num: int, total_rounds: int):
    """Форматирование сообщения для битвы фильмов"""
    message = f"⚔️ **РАУНД {round_num}/{total_rounds}**\n\n"
    message += "Выбирай лучший фильм:\n\n"
    
    # Фильм 1
    title1 = movie1.get('title', 'Без названия')
    overview1 = movie1.get('overview', 'Описание отсутствует')
    if len(overview1) > 100:
        overview1 = overview1[:97] + "..."
    
    message += f"🎬 **{title1}**\n"
    message += f"📝 {overview1}\n\n"
    
    # Фильм 2
    title2 = movie2.get('title', 'Без названия')
    overview2 = movie2.get('overview', 'Описание отсутствует')
    if len(overview2) > 100:
        overview2 = overview2[:97] + "..."
    
    message += f"🎬 **{title2}**\n"
    message += f"📝 {overview2}\n\n"
    
    message += "Кто победит в этом раунде?"
    
    return message

def format_battle_result(winner: dict, game_type: str):
    """Форматирование результата битвы"""
    title = winner.get('title', 'Без названия')
    overview = winner.get('overview', 'Описание отсутствует')
    
    if len(overview) > 150:
        overview = overview[:147] + "..."
    
    message = f"🏆 **ПОБЕДИТЕЛЬ!**\n\n"
    message += f"🎬 **{title}**\n"
    message += f"📝 {overview}\n\n"
    
    # Реферальные ссылки
    streaming_links = {
        'США': {
            'Netflix': "https://netflix.com",
            'Hulu': "https://hulu.com",
            'Amazon Prime': "https://amazon.com/primevideo"
        },
        'ЕС': {
            'Netflix': "https://netflix.com",
            'Disney+': "https://disneyplus.com",
            'HBO Max': "https://hbomax.com"
        },
        'СНГ': {
            'Кинопоиск': "https://kinopoisk.ru",
            'Okko': "https://okko.tv",
            'Ivi': "https://ivi.ru"
        }
    }
    
    # Выбираем несколько сервисов
    import random
    all_services = []
    for region, services in streaming_links.items():
        for service, link in services.items():
            all_services.append((service, link, region))
    
    num_services = random.randint(2, 3)
    selected_services = random.sample(all_services, min(num_services, len(all_services)))
    
    message += "🎥 **Где посмотреть:**\n"
    for service, link, region in selected_services:
        message += f"• [Смотреть на {service} ({region})]({link})\n"
    
    return message

def get_streaming_links():
    """Получение списка стриминговых сервисов"""
    return {
        'США': {
            'Netflix': "https://netflix.com",
            'Hulu': "https://hulu.com",
            'Amazon Prime': "https://amazon.com/primevideo"
        },
        'ЕС': {
            'Netflix': "https://netflix.com",
            'Disney+': "https://disneyplus.com",
            'HBO Max': "https://hbomax.com"
        },
        'СНГ': {
            'Кинопоиск': "https://kinopoisk.ru",
            'Okko': "https://okko.tv",
            'Ivi': "https://ivi.ru"
        }
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    save_user_state(user_id, GAME_STATES['WAITING_MODE'])
    
    keyboard = [
        [InlineKeyboardButton("🎮 Играть одному", callback_data="mode_single")],
        [InlineKeyboardButton("👥 Играть с друзьями", callback_data="mode_group")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Добро пожаловать в Movie Battle! 🎬\n\n"
        "Выбирай лучший фильм из 26, сравнивая их попарно.\n"
        "Играть одному или с друзьями?",
        reply_markup=reply_markup
    )

async def battle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /battle для группового режима"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Проверяем, что это группа
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "Команда /battle доступна только в группах! "
            "Добавь бота в группу и попробуй снова."
        )
        return
    
    # Создаем новую групповую игру
    movies = get_popular_movies(26)
    game_id = create_game(user_id, chat_id, 'group', movies)
    
    # Начинаем первый раунд
    await start_battle_round(update, context, game_id, movies)

async def start_battle_round(update, context, game_id, movies_list):
    """Начало раунда битвы"""
    import json
    
    # Получаем текущую игру
    game = get_current_game_by_id(game_id)
    if not game:
        return
    
    current_round = game[5]  # current_round
    total_rounds = game[6]   # total_rounds
    
    # Если фильмов осталось меньше 2, игра окончена
    if len(movies_list) < 2:
        winner = movies_list[0] if movies_list else None
        if winner:
            message = format_battle_result(winner, game[3])  # game_type
            keyboard = [[InlineKeyboardButton("🔄 Новая битва", callback_data="new_battle")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'edit_message_text'):
                await update.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # Выбираем пару фильмов
    movie1 = movies_list[0]
    movie2 = movies_list[1]
    
    # Создаем кнопки для голосования
    keyboard = [
        [
            InlineKeyboardButton(f"🎬 {movie1['title'][:20]}...", callback_data=f"vote_1_{game_id}"),
            InlineKeyboardButton(f"🎬 {movie2['title'][:20]}...", callback_data=f"vote_2_{game_id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем сообщение
    message = format_movie_battle(movie1, movie2, current_round, total_rounds)
    
    # Сохраняем текущую пару
    current_pair = json.dumps([movie1, movie2])
    update_game_round(game_id, current_round, current_pair)
    
    # Отправляем сообщение
    if hasattr(update, 'edit_message_text'):
        await update.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

def get_current_game_by_id(game_id: int):
    """Получение игры по ID"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM games WHERE game_id = ?', (game_id,))
    result = cursor.fetchone()
    conn.close()
    return result

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "mode_single":
        # Одиночный режим
        user_id = query.from_user.id
        chat_id = query.message.chat.id
        
        save_user_state(user_id, GAME_STATES['SINGLE_PLAYER'])
        
        # Создаем новую игру
        movies = get_popular_movies(26)
        game_id = create_game(user_id, chat_id, 'single', movies)
        
        # Начинаем первый раунд
        await start_battle_round(query, context, game_id, movies)
    
    elif query.data == "mode_group":
        # Групповой режим
        await query.edit_message_text(
            "👥 **Групповой режим**\n\n"
            "1. Добавь бота в Telegram-группу\n"
            "2. Отправь команду /battle в группе\n"
            "3. Участники будут голосовать за лучший фильм\n\n"
            "Готов начать групповую битву?",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("vote_"):
        # Обработка голосования
        parts = query.data.split("_")
        vote = int(parts[1])  # 1 или 2
        game_id = int(parts[2])
        
        await process_vote(query, context, game_id, vote)
    
    elif query.data == "new_battle":
        # Новая битва
        await start(query, context)
    
    # Убрали обработчик next_round, так как переход стал автоматическим

async def process_vote(query, context, game_id, vote):
    """Обработка голосования"""
    import json
    
    # Получаем текущую игру
    game = get_current_game_by_id(game_id)
    if not game:
        return
    
    game_type = game[3]  # game_type
    movies_json = game[4]  # movies_list
    current_round = game[5]  # current_round
    current_pair = game[7]  # current_pair
    votes_json = game[8]  # votes
    
    # Парсим данные
    movies_list = json.loads(movies_json)
    current_pair_movies = json.loads(current_pair) if current_pair else []
    votes = json.loads(votes_json) if votes_json else {}
    
    # Добавляем голос
    user_id = query.from_user.id
    votes[str(user_id)] = vote
    
    # Сохраняем голоса
    update_game_round(game_id, current_round, current_pair, json.dumps(votes))
    
    if game_type == 'single':
        # Одиночный режим - сразу определяем победителя
        winner = current_pair_movies[vote - 1]  # vote 1 или 2
        loser = current_pair_movies[2 - vote]   # противоположный
        
        # Удаляем проигравший фильм из списка
        movies_list.remove(loser)
        
        # Обновляем список фильмов в базе
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE games SET movies_list = ? WHERE game_id = ?', 
                      (json.dumps(movies_list), game_id))
        conn.commit()
        conn.close()
        
        # Если остался один фильм - игра окончена
        if len(movies_list) == 1:
            winner = movies_list[0]
            message = format_battle_result(winner, game_type)
            keyboard = [[InlineKeyboardButton("🔄 Новая битва", callback_data="new_battle")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            # Увеличиваем номер раунда и продолжаем игру
            increment_game_round(game_id)
            await start_battle_round(query, context, game_id, movies_list)
    
    else:
        # Групповой режим - показываем обновленные результаты голосования
        vote1_count = sum(1 for v in votes.values() if v == 1)
        vote2_count = sum(1 for v in votes.values() if v == 2)
        
        # Показываем кто проголосовал
        voter_name = query.from_user.first_name or query.from_user.username or "Участник"
        message = f"🗳️ **{voter_name}** проголосовал!\n\n"
        message += f"📊 **Текущие результаты:**\n"
        message += f"🎬 {current_pair_movies[0]['title']}: {vote1_count} голосов\n"
        message += f"🎬 {current_pair_movies[1]['title']}: {vote2_count} голосов\n\n"
        
        # Проверяем, нужно ли завершить раунд
        total_votes = len(votes)
        chat_members_count = await context.bot.get_chat_member_count(game[2])  # chat_id
        
        # Если проголосовали все участники или прошло достаточно времени, завершаем раунд
        if total_votes >= min(chat_members_count - 1, 10):  # -1 для бота, максимум 10 голосов
            await finish_group_round(query, context, game_id, movies_list, current_pair_movies, votes)
        else:
            # Показываем кнопки для продолжения голосования
            keyboard = [
                [
                    InlineKeyboardButton(f"🎬 {current_pair_movies[0]['title'][:15]}...", callback_data=f"vote_1_{game_id}"),
                    InlineKeyboardButton(f"🎬 {current_pair_movies[1]['title'][:15]}...", callback_data=f"vote_2_{game_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def finish_group_round(query, context, game_id, movies_list, current_pair_movies, votes):
    """Завершение раунда в групповом режиме"""
    import json
    
    vote1_count = sum(1 for v in votes.values() if v == 1)
    vote2_count = sum(1 for v in votes.values() if v == 2)
    
    message = f"📊 **Финальные результаты голосования:**\n\n"
    message += f"🎬 {current_pair_movies[0]['title']}: {vote1_count} голосов\n"
    message += f"🎬 {current_pair_movies[1]['title']}: {vote2_count} голосов\n\n"
    
    # Определяем победителя
    if vote1_count > vote2_count:
        winner = current_pair_movies[0]
        loser = current_pair_movies[1]
        message += f"🏆 **Победитель раунда:** {winner['title']}\n\n"
    elif vote2_count > vote1_count:
        winner = current_pair_movies[1]
        loser = current_pair_movies[0]
        message += f"🏆 **Победитель раунда:** {winner['title']}\n\n"
    else:
        # Ничья - случайный выбор
        winner = random.choice(current_pair_movies)
        loser = current_pair_movies[1] if winner == current_pair_movies[0] else current_pair_movies[0]
        message += f"🏆 **Победитель раунда (ничья):** {winner['title']}\n\n"
    
    # Удаляем проигравший фильм
    movies_list.remove(loser)
    
    # Обновляем список фильмов
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE games SET movies_list = ? WHERE game_id = ?', 
                  (json.dumps(movies_list), game_id))
    conn.commit()
    conn.close()
    
    # Если остался один фильм - игра окончена
    if len(movies_list) == 1:
        winner = movies_list[0]
        result_message = format_battle_result(winner, 'group')
        keyboard = [[InlineKeyboardButton("🔄 Новая битва", callback_data="new_battle")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(result_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        # Автоматически переходим к следующему раунду через 3 секунды
        message += "⏳ Переход к следующему раунду через 3 секунды..."
        await query.edit_message_text(message, parse_mode='Markdown')
        
        # Увеличиваем номер раунда
        increment_game_round(game_id)
        
        # Ждем 3 секунды и переходим к следующему раунду
        import asyncio
        await asyncio.sleep(3)
        await start_battle_round(query, context, game_id, movies_list)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

def main():
    """Основная функция"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в переменных окружения")
        return
    
    # Проверяем TMDb API ключ
    if not TMDB_API_KEY or TMDB_API_KEY == "placeholder_until_domain_ready":
        logger.info("TMDb API ключ не настроен, используем заглушки фильмов")
    else:
        logger.info("TMDb API ключ настроен")
    
    # Инициализируем базу данных
    init_database()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("battle", battle_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Movie Battle Bot запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 