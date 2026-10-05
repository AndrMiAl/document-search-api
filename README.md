# Поиск по документам

[![Тесты](https://github.com/AndrMiAl/document-search-api/actions/workflows/tests.yml/badge.svg)](https://github.com/AndrMiAl/document-search-api/actions/workflows/tests.yml)

Асинхронный поисковый сервис для корпуса из 1500 текстовых документов. Запрос ищется в Elasticsearch, а найденные записи и их поля возвращаются из PostgreSQL. Веб-интерфейс позволяет искать документы и удалять отдельные записи.

## Стек

Python 3.12 · FastAPI · SQLAlchemy Async · PostgreSQL · Elasticsearch · Docker Compose · Pytest

## Запуск

Требуется Docker Desktop с Docker Compose v2.

```powershell
docker compose up --build
```

Веб-интерфейс: [http://localhost:8000](http://localhost:8000).

При первом старте API создаёт схему и загружает `data/posts.csv`. При следующих стартах индекс Elasticsearch восстанавливается из PostgreSQL, поэтому удалённые документы не появляются снова. Данные хранятся в Docker volumes; `docker compose down -v` удаляет их вместе с контейнерами.

Остановка: `Ctrl+C` или `docker compose down`.

## Возможности

- Полнотекстовый поиск по полю `text`.
- До 20 результатов, сначала самые новые; каждый результат содержит `id`, `rubrics`, `text` и `created_date`.
- Удаление документа по `id` из PostgreSQL и Elasticsearch.
- Добавление документов через API.
- Автоматическая начальная загрузка корпуса из CSV.

## API

| Метод | Путь | Назначение |
| --- | --- | --- |
| `GET` | `/documents/search?q=текст` | Найти документы по тексту |
| `GET` | `/documents` | Получить последние 20 документов |
| `POST` | `/documents` | Добавить документы |
| `DELETE` | `/documents/{id}` | Удалить документ |
| `GET` | `/health` | Проверить доступность сервиса |
| `GET` | `/docs.json` | Получить схему OpenAPI в JSON |

Пример добавления документа:

```json
{
  "documents": [
    {
      "id": 1501,
      "rubrics": ["Новости"],
      "text": "Текст документа",
      "created_date": "2025-01-15T12:00:00Z"
    }
  ]
}
```

## Проверки

Тесты используют SQLite и тестовый поисковый индекс, поэтому для них не нужно запускать Docker:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
```

GitHub Actions запускает тот же набор тестов при каждом push и pull request в `main`.

## Данные

В репозитории находится корпус `data/posts.csv` из тестового задания. Исходная ссылка на набор данных: [Яндекс.Диск](https://disk.yandex.ru/d/UYooXd9q2yqTMQ).
