# Document Search API

Асинхронный HTTP-сервис для полнотекстового поиска документов. Полные записи хранятся в PostgreSQL, текст индексируется в Elasticsearch. Поиск возвращает не более 20 документов по убыванию даты создания.

## Запуск через Docker

Нужен Docker с Compose plugin.

```powershell
docker compose up --build
```

После запуска:

- Интерфейс поисковика: <http://localhost:8000/>

При первом запуске Docker сам создаёт таблицу, загружает 1500 документов из `data/posts.csv` и строит поисковый индекс. Подождите, пока в логах API появится `Готово документов в поисковом индексе: 1500`, затем откройте <http://localhost:8000/>. В следующих запусках CSV повторно не загружается, а поисковый индекс восстанавливается из PostgreSQL.

Остановить сервисы: `Ctrl+C` в окне запуска или `docker compose down`. Данные сохраняются в Docker volumes. Команда `docker compose down -v` удалит и сервисы, и все сохранённые данные.

## Загрузка CSV

CSV из задания содержит столбцы `text`, `created_date`, `rubrics`. Если поля `id` нет, импортер присваивает уникальный ID по номеру строки. Рубрики читаются как список строк, дата должна быть ISO 8601 или `YYYY-MM-DD HH:MM:SS`.

Набор данных из задания сохранён в `data/posts.csv` и входит в репозиторий, поэтому для обычного запуска отдельный импорт не требуется. Если CSV заменили или нужно вручную повторно синхронизировать его записи:

```powershell
docker compose up --build -d
docker compose run --rm api python -m scripts.import_csv /service/data/posts.csv
```

Скрипт обновляет записи с уже существующими ID, добавляет новые и пакетно синхронизирует Elasticsearch. Повторный запуск безопасен. Настройки подключения берутся из `DATABASE_URL`, `ELASTICSEARCH_URL` и `ELASTICSEARCH_INDEX`.

## API

Интерактивная документация скрыта, чтобы при открытии проекта пользователь попадал сразу в поисковый интерфейс. Схема API доступна в формате JSON по адресу `GET /docs.json`.

### Добавить документы

`POST /documents`

```json
{
  "documents": [
    {
      "id": 1,
      "rubrics": ["Новости"],
      "text": "Текст документа для поиска",
      "created_date": "2024-01-15T12:00:00Z"
    }
  ]
}
```

### Найти документы

`GET /documents/search?q=текст`

Возвращает до 20 совпадений с полями `id`, `rubrics`, `text` и `created_date`, начиная с самых новых.

### Удалить документ

`DELETE /documents/{id}`

Удаляет документ и из БД, и из Elasticsearch. Ответ: `204 No Content`; неизвестный ID возвращает `404`.

## Тесты

Для тестов нужен Python 3.12+.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

## Отправка в GitHub

Создайте на GitHub пустой репозиторий без README и лицензии. В этой папке сохраните файлы первым коммитом, затем подставьте адрес своего репозитория:

```powershell
git add .
git config user.name "Ваше имя"
git config user.email "ваш-email@example.com"
git commit -m "Initial project"
git remote add origin https://github.com/ВАШ-АККАУНТ/ИМЯ-РЕПОЗИТОРИЯ.git
git branch -M main
git push -u origin main
```

Если имя и email уже настроены в Git глобально, команды `git config` можно пропустить.

Файл `.env`, виртуальное окружение, кэш и локальные результаты в Git не попадают. `data/posts.csv` включён, чтобы Docker мог заполнить пустую базу после клонирования репозитория.
