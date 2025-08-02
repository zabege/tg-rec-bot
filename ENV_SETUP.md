# 🔧 Настройка переменных окружения

## Для локального запуска

Создайте файл `.env` в корне проекта со следующим содержимым:

```
BOT_TOKEN=7907134555:AAELsUjUcUiWnuekGQM7Y-8SbDZvoU1OKRc
TMDB_API_KEY=placeholder_until_domain_ready
```

## Для Railway

В настройках проекта Railway добавьте следующие переменные окружения:

- `BOT_TOKEN`: `7907134555:AAELsUjUcUiWnuekGQM7Y-8SbDZvoU1OKRc`
- `TMDB_API_KEY`: `placeholder_until_domain_ready`

## После получения домена

Когда у вас будет домен для TMDb API:

1. Получите API ключ на [themoviedb.org](https://www.themoviedb.org)
2. Замените `placeholder_until_domain_ready` на реальный API ключ
3. Бот автоматически переключится на использование реальных данных

## Безопасность

⚠️ **Важно**: Файл `.env` уже добавлен в `.gitignore` и не будет загружен в репозиторий.

Токен бота защищен от случайной публикации в коде. 