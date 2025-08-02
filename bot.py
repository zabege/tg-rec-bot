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
    'BATTLE_ACTIVE': 'battle_active',
    'SURVEY_GENRES': 'survey_genres',
    'SURVEY_TYPE': 'survey_type',
    'SURVEY_YEARS': 'survey_years'
}

# Жанры для опросника
GENRES = {
    'comedy': {'id': 35, 'name': 'Комедия'},
    'drama': {'id': 18, 'name': 'Драма'},
    'fantasy': {'id': 14, 'name': 'Фантастика'},
    'action': {'id': 28, 'name': 'Боевик'},
    'thriller': {'id': 53, 'name': 'Триллер'},
    'adventure': {'id': 12, 'name': 'Приключения'},
    'horror': {'id': 27, 'name': 'Ужасы'},
    'romance': {'id': 10749, 'name': 'Романтика'}
}

# Типы контента
CONTENT_TYPES = {
    'movie': 'Фильмы',
    'tv': 'Сериалы',
    'both': 'Оба'
}

# Годы выпуска
YEAR_RANGES = {
    'new': {'name': 'Новинки (2015-2025)', 'min': 2015, 'max': 2025},
    'classic': {'name': 'Классика (до 2000)', 'min': 1900, 'max': 2000},
    'all': {'name': 'Все года', 'min': 1900, 'max': 2025}
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
            survey_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица опросников
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS surveys (
            survey_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            selected_genres TEXT,
            content_type TEXT,
            year_range TEXT,
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

def save_survey_data(user_id: int, chat_id: int, selected_genres: list, content_type: str, year_range: str):
    """Сохранение данных опросника"""
    import json
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    genres_json = json.dumps(selected_genres)
    
    cursor.execute('''
        INSERT OR REPLACE INTO surveys (user_id, chat_id, selected_genres, content_type, year_range)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, chat_id, genres_json, content_type, year_range))
    
    conn.commit()
    conn.close()

def get_survey_data(user_id: int, chat_id: int):
    """Получение данных опросника"""
    import json
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT selected_genres, content_type, year_range 
        FROM surveys 
        WHERE user_id = ? AND chat_id = ?
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id, chat_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'selected_genres': json.loads(result[0]),
            'content_type': result[1],
            'year_range': result[2]
        }
    return None

def get_active_group_game(chat_id: int):
    """Получение активной игры в группе"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM games 
        WHERE chat_id = ? AND game_type = 'group'
        ORDER BY created_at DESC LIMIT 1
    ''', (chat_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result

def get_group_survey_data(chat_id: int):
    """Получение данных группового опросника"""
    import json
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT selected_genres, content_type, year_range 
        FROM surveys 
        WHERE chat_id = ?
        ORDER BY created_at DESC
    ''', (chat_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        return None
    
    # Объединяем данные всех участников
    all_genres = []
    content_types = {}
    year_ranges = {}
    
    for result in results:
        genres = json.loads(result[0])
        content_type = result[1]
        year_range = result[2]
        
        all_genres.extend(genres)
        content_types[content_type] = content_types.get(content_type, 0) + 1
        year_ranges[year_range] = year_ranges.get(year_range, 0) + 1
    
    # Выбираем наиболее популярные варианты
    most_popular_content = max(content_types.items(), key=lambda x: x[1])[0]
    most_popular_year = max(year_ranges.items(), key=lambda x: x[1])[0]
    
    # Убираем дубликаты жанров и берем топ-3
    unique_genres = list(set(all_genres))
    genre_counts = {}
    for genre in all_genres:
        genre_counts[genre] = genre_counts.get(genre, 0) + 1
    
    top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    selected_genres = [genre for genre, count in top_genres]
    
    return {
        'selected_genres': selected_genres,
        'content_type': most_popular_content,
        'year_range': most_popular_year
    }

def get_movies_by_survey(selected_genres: list, content_type: str, year_range: str, count: int = 26):
    """Получение фильмов на основе опросника"""
    try:
        # Проверяем, есть ли валидный API ключ
        if TMDB_API_KEY and TMDB_API_KEY != "placeholder_until_domain_ready":
            # Определяем endpoint в зависимости от типа контента
            if content_type == 'tv':
                url = f"{TMDB_BASE_URL}/discover/tv"
            else:
                url = f"{TMDB_BASE_URL}/discover/movie"
            
            # Формируем параметры запроса
            params = {
                'api_key': TMDB_API_KEY,
                'language': 'ru-RU',
                'sort_by': 'popularity.desc',
                'include_adult': False,
                'page': 1
            }
            
            # Добавляем жанры
            if selected_genres:
                genre_ids = [GENRES[genre]['id'] for genre in selected_genres if genre in GENRES]
                if genre_ids:
                    params['with_genres'] = ','.join(map(str, genre_ids))
            
            # Добавляем годы
            year_config = YEAR_RANGES.get(year_range, YEAR_RANGES['all'])
            params['primary_release_date.gte'] = f"{year_config['min']}-01-01"
            params['primary_release_date.lte'] = f"{year_config['max']}-12-31"
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            movies = data.get('results', [])
            
            # Если фильмов недостаточно, добавляем популярные
            if len(movies) < count:
                popular_movies = get_popular_movies(count * 2)
                movies.extend(popular_movies)
            
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
    
    message += f"🎬 **{title1}**\n"
    message += f"📝 {overview1}\n\n"
    
    # Фильм 2
    title2 = movie2.get('title', 'Без названия')
    overview2 = movie2.get('overview', 'Описание отсутствует')
    
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
    
    # Проверяем, есть ли активная игра в группе
    active_game = get_active_group_game(chat_id)
    
    if active_game:
        # Если игра уже идет, присоединяемся к ней
        await join_existing_game(update, context, active_game)
    else:
        # Начинаем новый опросник для группы
        await start_group_survey(update, context)

async def start_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало опросника"""
    user_id = update.effective_user.id
    save_user_state(user_id, GAME_STATES['SURVEY_GENRES'])
    
    # Создаем кнопки для выбора жанров
    keyboard = []
    for genre_key, genre_info in GENRES.items():
        keyboard.append([InlineKeyboardButton(
            genre_info['name'], 
            callback_data=f"survey_genre_{genre_key}"
        )])
    
    # Кнопка для завершения выбора жанров
    keyboard.append([InlineKeyboardButton("✅ Завершить выбор", callback_data="survey_genres_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Вопрос 1: Жанры**\n\n"
    message += "Какие жанры тебе нравятся? Выбери до 3.\n"
    message += "Нажми на жанр, чтобы выбрать/отменить."
    
    if hasattr(update, 'edit_message_text'):
        await update.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def start_group_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало группового опросника"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Проверяем, не проходил ли пользователь уже опросник
    existing_survey = get_survey_data(user_id, chat_id)
    if existing_survey:
        # Показываем статус опросника
        survey_count = get_survey_participants_count(chat_id)
        chat_members_count = await update.bot.get_chat_member_count(chat_id)
        
        message = "✅ **Ты уже проходил опросник в этой группе!**\n\n"
        message += f"📊 Прошли опросник: {survey_count}/{chat_members_count - 1} участников\n"
        
        if survey_count >= min(chat_members_count - 1, 3):
            message += "\n🎮 Все участники завершили опросник! Игра должна начаться скоро..."
        else:
            message += "\n⏳ Ждем других участников..."
        
        await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    save_user_state(user_id, GAME_STATES['SURVEY_GENRES'])
    
    # Создаем кнопки для выбора жанров
    keyboard = []
    for genre_key, genre_info in GENRES.items():
        keyboard.append([InlineKeyboardButton(
            genre_info['name'], 
            callback_data=f"group_survey_genre_{genre_key}"
        )])
    
    # Кнопка для завершения выбора жанров
    keyboard.append([InlineKeyboardButton("✅ Завершить выбор", callback_data="group_survey_genres_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Групповой опросник - Вопрос 1: Жанры**\n\n"
    message += "Какие жанры тебе нравятся? Выбери до 3.\n"
    message += "Нажми на жанр, чтобы выбрать/отменить."
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def join_existing_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Присоединение к существующей игре"""
    import json
    
    game = get_active_group_game(update.effective_chat.id)
    if not game:
        return
    
    movies_json = game[4]  # movies_list
    movies_list = json.loads(movies_json)
    
    message = "🎮 **Присоединяемся к активной игре!**\n\n"
    message += "Голосование уже идет. Выбирай лучший фильм!"
    
    # Показываем текущую пару фильмов
    if len(movies_list) >= 2:
        movie1 = movies_list[0]
        movie2 = movies_list[1]
        
        message += f"\n\n🎬 **{movie1['title']}**\n"
        message += f"📝 {movie1.get('overview', 'Описание отсутствует')}\n\n"
        message += f"🎬 **{movie2['title']}**\n"
        message += f"📝 {movie2.get('overview', 'Описание отсутствует')}\n\n"
        
        # Создаем кнопки для голосования с полными названиями
        keyboard = [
            [
                InlineKeyboardButton(f"🎬 {movie1['title']}", callback_data=f"vote_1_{game[0]}"),
                InlineKeyboardButton(f"🎬 {movie2['title']}", callback_data=f"vote_2_{game[0]}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, parse_mode='Markdown')

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
        # Для группового режима отправляем новое сообщение в группу
        if hasattr(update, 'message') and update.message.chat.type != 'private':
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
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
        # Одиночный режим - начинаем с опросника
        await start_survey(query, context)
    
    elif query.data == "mode_group":
        # Групповой режим
        await query.edit_message_text(
            "👥 **Групповой режим**\n\n"
            "1. Добавь бота в Telegram-группу\n"
            "2. Отправь команду /battle в группе\n"
            "3. Пройди опросник для персонализации\n"
            "4. Участники будут голосовать за лучший фильм\n\n"
            "Готов начать групповую битву?",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("survey_genre_"):
        # Обработка выбора жанра в опроснике
        await handle_survey_genre_selection(query, context)
    
    elif query.data == "survey_genres_done":
        # Завершение выбора жанров
        await handle_survey_genres_done(query, context)
    
    elif query.data.startswith("survey_type_"):
        # Обработка выбора типа контента
        await handle_survey_type_selection(query, context)
    
    elif query.data.startswith("survey_year_"):
        # Обработка выбора года
        await handle_survey_year_selection(query, context)
    
    elif query.data.startswith("group_survey_genre_"):
        # Обработка выбора жанра в групповом опроснике
        await handle_group_survey_genre_selection(query, context)
    
    elif query.data == "group_survey_genres_done":
        # Завершение выбора жанров в групповом опроснике
        await handle_group_survey_genres_done(query, context)
    
    elif query.data.startswith("group_survey_type_"):
        # Обработка выбора типа контента в групповом опроснике
        await handle_group_survey_type_selection(query, context)
    
    elif query.data.startswith("group_survey_year_"):
        # Обработка выбора года в групповом опроснике
        await handle_group_survey_year_selection(query, context)
    
    elif query.data.startswith("vote_"):
        # Обработка голосования
        parts = query.data.split("_")
        vote = int(parts[1])  # 1 или 2
        game_id = int(parts[2])
        
        await process_vote(query, context, game_id, vote)
    
    elif query.data.startswith("finish_round_"):
        # Принудительное завершение раунда
        game_id = int(query.data.split("_")[2])
        await finish_round_manually(query, context, game_id)
    
    elif query.data == "new_battle":
        # Новая битва
        await start(query, context)

async def handle_group_survey_genre_selection(query, context):
    """Обработка выбора жанра в групповом опроснике"""
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    genre_key = query.data.replace("group_survey_genre_", "")
    
    # Получаем текущие выбранные жанры из контекста
    if 'selected_genres' not in context.user_data:
        context.user_data['selected_genres'] = []
    
    selected_genres = context.user_data['selected_genres']
    
    # Переключаем выбор жанра
    if genre_key in selected_genres:
        selected_genres.remove(genre_key)
    else:
        if len(selected_genres) < 3:
            selected_genres.append(genre_key)
    
    # Обновляем кнопки
    keyboard = []
    for g_key, g_info in GENRES.items():
        button_text = f"✅ {g_info['name']}" if g_key in selected_genres else g_info['name']
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"group_survey_genre_{g_key}"
        )])
    
    # Кнопка для завершения
    keyboard.append([InlineKeyboardButton("✅ Завершить выбор", callback_data="group_survey_genres_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Групповой опросник - Вопрос 1: Жанры**\n\n"
    message += "Какие жанры тебе нравятся? Выбери до 3.\n"
    message += f"Выбрано: {len(selected_genres)}/3\n"
    
    if selected_genres:
        selected_names = [GENRES[g]['name'] for g in selected_genres]
        message += f"Выбранные жанры: {', '.join(selected_names)}"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_group_survey_genres_done(query, context):
    """Завершение выбора жанров в групповом опроснике"""
    user_id = query.from_user.id
    
    if 'selected_genres' not in context.user_data or not context.user_data['selected_genres']:
        await query.answer("Выбери хотя бы один жанр!")
        return
    
    save_user_state(user_id, GAME_STATES['SURVEY_TYPE'])
    
    # Создаем кнопки для выбора типа контента
    keyboard = []
    for type_key, type_name in CONTENT_TYPES.items():
        keyboard.append([InlineKeyboardButton(
            type_name, 
            callback_data=f"group_survey_type_{type_key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Групповой опросник - Вопрос 2: Тип контента**\n\n"
    message += "Хочешь фильмы или сериалы?"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_group_survey_type_selection(query, context):
    """Обработка выбора типа контента в групповом опроснике"""
    user_id = query.from_user.id
    content_type = query.data.replace("group_survey_type_", "")
    
    context.user_data['content_type'] = content_type
    save_user_state(user_id, GAME_STATES['SURVEY_YEARS'])
    
    # Создаем кнопки для выбора года
    keyboard = []
    for year_key, year_info in YEAR_RANGES.items():
        keyboard.append([InlineKeyboardButton(
            year_info['name'], 
            callback_data=f"group_survey_year_{year_key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Групповой опросник - Вопрос 3: Годы выпуска**\n\n"
    message += "Фильмы какого времени?"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_group_survey_year_selection(query, context):
    """Обработка выбора года в групповом опроснике"""
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    year_range = query.data.replace("group_survey_year_", "")
    
    # Сохраняем данные опросника пользователя
    selected_genres = context.user_data.get('selected_genres', [])
    content_type = context.user_data.get('content_type', 'movie')
    
    save_survey_data(user_id, chat_id, selected_genres, content_type, year_range)
    
    # Показываем сообщение о завершении опросника
    selected_genres_names = [GENRES[g]['name'] for g in selected_genres]
    content_type_name = CONTENT_TYPES[content_type]
    year_range_name = YEAR_RANGES[year_range]['name']
    
    message = "✅ **Твой опросник завершен!**\n\n"
    message += f"🎬 Твои жанры: {', '.join(selected_genres_names)}\n"
    message += f"📺 Твой тип: {content_type_name}\n"
    message += f"📅 Твои годы: {year_range_name}\n\n"
    
    # Проверяем, сколько участников прошли опросник
    survey_count = get_survey_participants_count(chat_id)
    chat_members_count = await query.bot.get_chat_member_count(chat_id)
    
    message += f"📊 Прошли опросник: {survey_count}/{chat_members_count - 1} участников\n"
    
    # Если прошли опросник все участники или большинство, начинаем игру
    if survey_count >= min(chat_members_count - 1, 3):  # -1 для бота, минимум 3 участника
        message += "\n🎮 Все участники завершили опросник! Начинаем игру..."
        await query.edit_message_text(message, parse_mode='Markdown')
        
        # Небольшая задержка для показа сообщения
        import asyncio
        await asyncio.sleep(2)
        
        await start_group_game_from_survey(query, context, chat_id)
    else:
        message += "\n⏳ Ждем других участников..."
        await query.edit_message_text(message, parse_mode='Markdown')

def get_survey_participants_count(chat_id: int):
    """Получение количества участников, прошедших опросник"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT user_id) 
        FROM surveys 
        WHERE chat_id = ?
    ''', (chat_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

async def start_group_game_from_survey(query, context, chat_id):
    """Запуск групповой игры на основе опросника"""
    # Получаем объединенные данные опросника
    survey_data = get_group_survey_data(chat_id)
    
    if not survey_data:
        await query.edit_message_text("❌ Ошибка: данные опросника не найдены")
        return
    
    # Получаем фильмы на основе опросника
    movies = get_movies_by_survey(
        survey_data['selected_genres'],
        survey_data['content_type'],
        survey_data['year_range'],
        26
    )
    
    # Создаем игру
    user_id = query.from_user.id
    game_id = create_game(user_id, chat_id, 'group', movies)
    
    # Показываем результат опросника в группе
    selected_genres_names = [GENRES[g]['name'] for g in survey_data['selected_genres']]
    content_type_name = CONTENT_TYPES[survey_data['content_type']]
    year_range_name = YEAR_RANGES[survey_data['year_range']]['name']
    
    message = "🎮 **Групповой опросник завершен!**\n\n"
    message += f"🎬 Итоговые жанры: {', '.join(selected_genres_names)}\n"
    message += f"📺 Итоговый тип: {content_type_name}\n"
    message += f"📅 Итоговые годы: {year_range_name}\n\n"
    message += "⚔️ Начинаем битву фильмов!"
    
    # Отправляем сообщение в группу
    await context.bot.send_message(chat_id, message, parse_mode='Markdown')
    
    # Начинаем первый раунд - создаем фейковый update для группового сообщения
    class FakeUpdate:
        def __init__(self, chat_id, bot):
            self.message = type('Message', (), {'chat': type('Chat', (), {'id': chat_id, 'type': 'group'})})()
            self.bot = bot
    
    fake_update = FakeUpdate(chat_id, context.bot)
    await start_battle_round(fake_update, context, game_id, movies)

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
    
    # Проверяем, не голосовал ли уже этот пользователь
    if str(user_id) in votes:
        await query.answer("Ты уже проголосовал в этом раунде!")
        return
    
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
        
        # Показываем список проголосовавших
        if votes:
            voted_users = []
            for user_id_str in votes.keys():
                # Здесь можно было бы получить имена пользователей, но пока показываем количество
                voted_users.append(f"👤 Участник {len(voted_users) + 1}")
            
            message += f"✅ **Проголосовали:** {', '.join(voted_users)}\n\n"
        
        # Показываем полные описания фильмов
        message += f"🎬 **{current_pair_movies[0]['title']}**\n"
        message += f"📝 {current_pair_movies[0].get('overview', 'Описание отсутствует')}\n\n"
        message += f"🎬 **{current_pair_movies[1]['title']}**\n"
        message += f"📝 {current_pair_movies[1].get('overview', 'Описание отсутствует')}\n\n"
        
        # Проверяем, нужно ли завершить раунд
        total_votes = len(votes)
        chat_members_count = await context.bot.get_chat_member_count(game[2])  # chat_id
        
        # Показываем прогресс голосования
        message += f"📊 **Прогресс:** {total_votes}/{chat_members_count - 1} участников проголосовали\n\n"
        
        # Завершаем раунд только если проголосовали все участники или минимум 3 участника
        min_votes_required = max(3, min(chat_members_count - 1, 5))  # Минимум 3, максимум 5 голосов
        
        if total_votes >= min_votes_required:
            # Добавляем кнопку для принудительного завершения раунда
            keyboard = [
                [
                    InlineKeyboardButton(f"🎬 {current_pair_movies[0]['title']}", callback_data=f"vote_1_{game_id}"),
                    InlineKeyboardButton(f"🎬 {current_pair_movies[1]['title']}", callback_data=f"vote_2_{game_id}")
                ],
                [InlineKeyboardButton("✅ Завершить раунд", callback_data=f"finish_round_{game_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            # Показываем кнопки для продолжения голосования
            keyboard = [
                [
                    InlineKeyboardButton(f"🎬 {current_pair_movies[0]['title']}", callback_data=f"vote_1_{game_id}"),
                    InlineKeyboardButton(f"🎬 {current_pair_movies[1]['title']}", callback_data=f"vote_2_{game_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def finish_round_manually(query, context, game_id):
    """Принудительное завершение раунда"""
    import json
    
    # Получаем текущую игру
    game = get_current_game_by_id(game_id)
    if not game:
        return
    
    movies_json = game[4]  # movies_list
    current_pair = game[7]  # current_pair
    votes_json = game[8]  # votes
    
    # Парсим данные
    movies_list = json.loads(movies_json)
    current_pair_movies = json.loads(current_pair) if current_pair else []
    votes = json.loads(votes_json) if votes_json else {}
    
    await finish_group_round(query, context, game_id, movies_list, current_pair_movies, votes)

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

async def handle_survey_genre_selection(query, context):
    """Обработка выбора жанра в опроснике"""
    user_id = query.from_user.id
    genre_key = query.data.replace("survey_genre_", "")
    
    # Получаем текущие выбранные жанры из контекста
    if 'selected_genres' not in context.user_data:
        context.user_data['selected_genres'] = []
    
    selected_genres = context.user_data['selected_genres']
    
    # Переключаем выбор жанра
    if genre_key in selected_genres:
        selected_genres.remove(genre_key)
    else:
        if len(selected_genres) < 3:
            selected_genres.append(genre_key)
    
    # Обновляем кнопки
    keyboard = []
    for g_key, g_info in GENRES.items():
        button_text = f"✅ {g_info['name']}" if g_key in selected_genres else g_info['name']
        keyboard.append([InlineKeyboardButton(
            button_text, 
            callback_data=f"survey_genre_{g_key}"
        )])
    
    # Кнопка для завершения
    keyboard.append([InlineKeyboardButton("✅ Завершить выбор", callback_data="survey_genres_done")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Вопрос 1: Жанры**\n\n"
    message += "Какие жанры тебе нравятся? Выбери до 3.\n"
    message += f"Выбрано: {len(selected_genres)}/3\n"
    
    if selected_genres:
        selected_names = [GENRES[g]['name'] for g in selected_genres]
        message += f"Выбранные жанры: {', '.join(selected_names)}"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_survey_genres_done(query, context):
    """Завершение выбора жанров"""
    user_id = query.from_user.id
    
    if 'selected_genres' not in context.user_data or not context.user_data['selected_genres']:
        await query.answer("Выбери хотя бы один жанр!")
        return
    
    save_user_state(user_id, GAME_STATES['SURVEY_TYPE'])
    
    # Создаем кнопки для выбора типа контента
    keyboard = []
    for type_key, type_name in CONTENT_TYPES.items():
        keyboard.append([InlineKeyboardButton(
            type_name, 
            callback_data=f"survey_type_{type_key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Вопрос 2: Тип контента**\n\n"
    message += "Хочешь фильмы или сериалы?"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_survey_type_selection(query, context):
    """Обработка выбора типа контента"""
    user_id = query.from_user.id
    content_type = query.data.replace("survey_type_", "")
    
    context.user_data['content_type'] = content_type
    save_user_state(user_id, GAME_STATES['SURVEY_YEARS'])
    
    # Создаем кнопки для выбора года
    keyboard = []
    for year_key, year_info in YEAR_RANGES.items():
        keyboard.append([InlineKeyboardButton(
            year_info['name'], 
            callback_data=f"survey_year_{year_key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🎬 **Вопрос 3: Годы выпуска**\n\n"
    message += "Фильмы какого времени?"
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_survey_year_selection(query, context):
    """Обработка выбора года и завершение опросника"""
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    year_range = query.data.replace("survey_year_", "")
    
    # Сохраняем все данные опросника
    selected_genres = context.user_data.get('selected_genres', [])
    content_type = context.user_data.get('content_type', 'movie')
    
    save_survey_data(user_id, chat_id, selected_genres, content_type, year_range)
    
    # Получаем фильмы на основе опросника
    movies = get_movies_by_survey(selected_genres, content_type, year_range, 26)
    
    # Создаем игру (одиночный режим)
    game_id = create_game(user_id, chat_id, 'single', movies)
    
    # Показываем результат опросника
    selected_genres_names = [GENRES[g]['name'] for g in selected_genres]
    content_type_name = CONTENT_TYPES[content_type]
    year_range_name = YEAR_RANGES[year_range]['name']
    
    message = "✅ **Опросник завершен!**\n\n"
    message += f"🎬 Жанры: {', '.join(selected_genres_names)}\n"
    message += f"📺 Тип: {content_type_name}\n"
    message += f"📅 Годы: {year_range_name}\n\n"
    message += "🎮 Начинаем битву фильмов!"
    
    await query.edit_message_text(message, parse_mode='Markdown')
    
    # Начинаем первый раунд
    await start_battle_round(query, context, game_id, movies)

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