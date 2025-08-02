import os
import logging
import sqlite3
import requests
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

# Жанры фильмов
GENRES = {
    'comedy': {'id': 35, 'name': 'Комедия'},
    'drama': {'id': 18, 'name': 'Драма'},
    'fantasy': {'id': 14, 'name': 'Фантастика'},
    'action': {'id': 28, 'name': 'Боевик'}
}

def init_database():
    """Инициализация базы данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            genre TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_user_genre(user_id: int, genre: str):
    """Сохранение выбранного жанра пользователя"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, genre) 
        VALUES (?, ?)
    ''', (user_id, genre))
    conn.commit()
    conn.close()

def get_movies_by_genre(genre_id: int, page: int = 1):
    """Получение фильмов по жанру из TMDb API или заглушки"""
    try:
        # Проверяем, есть ли валидный API ключ
        if TMDB_API_KEY and TMDB_API_KEY != "placeholder_until_domain_ready":
            url = f"{TMDB_BASE_URL}/discover/movie"
            params = {
                'api_key': TMDB_API_KEY,
                'language': 'ru-RU',
                'with_genres': genre_id,
                'sort_by': 'popularity.desc',
                'page': page,
                'include_adult': False
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            return data.get('results', [])[:3]  # Возвращаем только 3 фильма
        else:
            # Возвращаем заглушки фильмов
            return get_mock_movies_by_genre(genre_id, page)
        
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к TMDb API: {e}")
        # Возвращаем заглушки при ошибке API
        return get_mock_movies_by_genre(genre_id, page)

def get_mock_movies_by_genre(genre_id: int, page: int = 1):
    """Заглушки фильмов для работы без TMDb API"""
    mock_movies = {
        35: [  # Комедия
            {
                'title': 'Джокер',
                'overview': 'История становления одного из самых известных злодеев комиксов. Артур Флек, неудачливый комедиант, постепенно превращается в преступного гения Джокера.'
            },
            {
                'title': 'Мальчишник в Вегасе',
                'overview': 'Четверо друзей отправляются в Лас-Вегас на мальчишник, но просыпаются на следующее утро и не помнят, что произошло прошлой ночью.'
            },
            {
                'title': 'Мертвые поэты',
                'overview': 'История о группе студентов и их вдохновляющем учителе, который учит их ценить поэзию и следовать своим мечтам.'
            }
        ],
        18: [  # Драма
            {
                'title': 'Побег из Шоушенка',
                'overview': 'История о надежде и дружбе в тюрьме Шоушенк, где банкир Энди Дюфрейн находит смысл жизни в самых неожиданных местах.'
            },
            {
                'title': 'Крёстный отец',
                'overview': 'Эпическая сага о семье Корлеоне, одной из пяти мафиозных семей Нью-Йорка, и их борьбе за власть и уважение.'
            },
            {
                'title': 'Форрест Гамп',
                'overview': 'История простого человека с добрым сердцем, который случайно становится свидетелем и участником важных событий американской истории.'
            }
        ],
        14: [  # Фантастика
            {
                'title': 'Матрица',
                'overview': 'Мир, в котором человечество порабощено машинами, а реальность оказывается компьютерной симуляцией. Нео должен спасти человечество.'
            },
            {
                'title': 'Интерстеллар',
                'overview': 'Группа исследователей отправляется через червоточину в поисках нового дома для человечества, пока Земля умирает.'
            },
            {
                'title': 'Бегущий по лезвию',
                'overview': 'Детектив в футуристическом Лос-Анджелесе должен найти и уничтожить репликантов - искусственных людей, созданных для работы в космосе.'
            }
        ],
        28: [  # Боевик
            {
                'title': 'Терминатор 2: Судный день',
                'overview': 'Кибернетический организм из будущего отправляется в прошлое, чтобы защитить молодого Джона Коннора от более продвинутого терминатора.'
            },
            {
                'title': 'Мадагаскар',
                'overview': 'Четыре животных из зоопарка случайно оказываются на острове Мадагаскар и должны научиться выживать в дикой природе.'
            },
            {
                'title': 'Миссия невыполнима',
                'overview': 'Агент Итан Хант должен доказать свою невиновность и раскрыть заговор, связанный с украденным списком агентов.'
            }
        ]
    }
    
    # Возвращаем фильмы для указанного жанра
    return mock_movies.get(genre_id, [])[:3]

def format_movie_message(movies: list, genre_name: str):
    """Форматирование сообщения с фильмами"""
    if not movies:
        return "К сожалению, не удалось найти фильмы для этого жанра. Попробуйте позже."
    
    message = f"🎬 Рекомендации в жанре '{genre_name}':\n\n"
    
    for i, movie in enumerate(movies, 1):
        title = movie.get('title', 'Без названия')
        overview = movie.get('overview', 'Описание отсутствует')
        
        # Обрезаем описание если оно слишком длинное
        if len(overview) > 150:
            overview = overview[:147] + "..."
        
        # Реферальная ссылка на Netflix (заглушка)
        netflix_link = "https://netflix.com/referral"
        
        message += f"{i}. **{title}**\n"
        message += f"📝 {overview}\n"
        message += f"🎥 [Смотреть на Netflix]({netflix_link})\n\n"
    
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = []
    for genre_key, genre_info in GENRES.items():
        keyboard.append([InlineKeyboardButton(
            genre_info['name'], 
            callback_data=f"genre_{genre_key}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Я помогу найти фильмы. Выбери жанр!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("genre_"):
        genre_key = query.data.replace("genre_", "")
        genre_info = GENRES.get(genre_key)
        
        if not genre_info:
            await query.edit_message_text("Неизвестный жанр. Попробуйте снова.")
            return
        
        # Сохраняем выбор пользователя
        save_user_genre(query.from_user.id, genre_key)
        
        # Получаем фильмы
        movies = get_movies_by_genre(genre_info['id'])
        message = format_movie_message(movies, genre_info['name'])
        
        # Кнопка для новых рекомендаций
        keyboard = [
            [InlineKeyboardButton("Ещё рекомендации", callback_data=f"more_{genre_key}_1")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("more_"):
        # Обработка кнопки "Ещё рекомендации"
        parts = query.data.split("_")
        if len(parts) >= 3:
            genre_key = parts[1]
            page = int(parts[2]) + 1
            genre_info = GENRES.get(genre_key)
            
            if not genre_info:
                await query.edit_message_text("Ошибка. Попробуйте выбрать жанр заново.")
                return
            
            # Получаем новые фильмы
            movies = get_movies_by_genre(genre_info['id'], page)
            message = format_movie_message(movies, genre_info['name'])
            
            # Обновляем кнопку
            keyboard = [
                [InlineKeyboardButton("Ещё рекомендации", callback_data=f"more_{genre_key}_{page}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

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
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 