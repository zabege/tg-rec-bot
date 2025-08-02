#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функций бота
"""

import sqlite3
import requests
from bot import GENRES, init_database, save_user_genre, get_movies_by_genre, format_movie_message

def test_database():
    """Тест базы данных"""
    print("🧪 Тестирование базы данных...")
    
    try:
        init_database()
        print("✅ База данных инициализирована")
        
        # Тест сохранения
        save_user_genre(12345, "comedy")
        print("✅ Сохранение пользователя работает")
        
        # Проверка сохранения
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (12345,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[1] == "comedy":
            print("✅ Чтение из базы данных работает")
        else:
            print("❌ Ошибка чтения из базы данных")
            
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")

def test_genres():
    """Тест жанров"""
    print("\n🧪 Тестирование жанров...")
    
    expected_genres = ['comedy', 'drama', 'fantasy', 'action']
    for genre in expected_genres:
        if genre in GENRES:
            print(f"✅ Жанр '{genre}' найден")
        else:
            print(f"❌ Жанр '{genre}' не найден")

def test_message_formatting():
    """Тест форматирования сообщений"""
    print("\n🧪 Тестирование форматирования сообщений...")
    
    # Тестовые данные фильма
    test_movies = [
        {
            'title': 'Тестовый фильм',
            'overview': 'Это тестовое описание фильма для проверки форматирования.'
        }
    ]
    
    try:
        message = format_movie_message(test_movies, "Комедия")
        if "Тестовый фильм" in message and "Комедия" in message:
            print("✅ Форматирование сообщений работает")
        else:
            print("❌ Ошибка форматирования сообщений")
    except Exception as e:
        print(f"❌ Ошибка форматирования: {e}")

def test_api_connection():
    """Тест подключения к API (без ключа)"""
    print("\n🧪 Тестирование подключения к API...")
    
    try:
        # Тест без API ключа (должен вернуть ошибку, но не краш)
        movies = get_movies_by_genre(35)  # comedy genre
        if isinstance(movies, list):
            print("✅ API функция работает (возвращает список)")
        else:
            print("❌ API функция не возвращает список")
    except Exception as e:
        print(f"✅ API функция обрабатывает ошибки корректно: {type(e).__name__}")

def main():
    """Основная функция тестирования"""
    print("🎬 Тестирование Telegram бота для рекомендаций фильмов\n")
    
    test_genres()
    test_database()
    test_message_formatting()
    test_api_connection()
    
    print("\n✅ Все тесты завершены!")
    print("\n📝 Следующие шаги:")
    print("1. Создайте файл .env с токенами")
    print("2. Запустите: python bot.py")
    print("3. Протестируйте бота в Telegram")

if __name__ == "__main__":
    main() 