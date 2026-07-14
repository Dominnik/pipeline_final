# TESTING

Документ описывает автоматические проверки и ручные сценарии для LLM Summary Service.

## Автоматические проверки

Основная локальная команда:

```bash
make check
```

Она запускает lint, проверку форматирования, тесты и компиляцию Python-модулей.

Команды, совпадающие с проверками CI:

```bash
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest
python -m compileall app
```

Фактическая локальная проверка после финальной ручной проверки выполнена 2026-07-13:

| Проверка | Фактический результат |
|---|---|
| `python -m pip check` | `No broken requirements found.` |
| `python -m ruff check .` | `All checks passed!` |
| `python -m ruff format --check .` | `25 files already formatted` |
| `python -m pytest` | `84 passed` |
| `python -m compileall app` | успешно |
| `make check` | успешно, включая `84 passed` |

## Ручной сценарий 1: health без ключа

Убедитесь, что `OPENAI_API_KEY` отсутствует или пуст в текущем окружении. Не удаляйте чужой `.env`: при необходимости временно установите в локальном `.env` пустое значение.

```text
OPENAI_API_KEY=
```

Затем запустите сервис:

```bash
make run
```

В другом терминале:

```bash
curl -i http://127.0.0.1:8000/health
```

Ожидаемый результат:

- HTTP 200;
- `status` равен `degraded`;
- `llm_configured` равен `false`.

Фактический результат 2026-07-13:

- HTTP 200;
- `status=degraded`;
- `llm_configured=false`;
- выполнено.

Пример формата:

```json
{
  "status": "degraded",
  "app_env": "local",
  "llm_configured": false
}
```

## Ручной сценарий 2: fallback

Запустите сервис без ключа. Для этого в локальном `.env` оставьте пустое значение:

```text
OPENAI_API_KEY=
```

Затем:

```bash
make run
```

Отправьте валидный запрос:

```bash
curl -i -X POST http://127.0.0.1:8000/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Это валидный текст для проверки fallback-сценария. Он содержит несколько предложений и проходит ограничения валидации.",
    "max_sentences": 2
  }'
```

Ожидаемый результат:

- HTTP 200;
- `source` равен `fallback`;
- `degraded` равен `true`;
- `cached` равен `false`;
- `summary` не пустой;
- заголовок `X-Request-ID` совпадает с `request_id` в JSON.

Фактический результат 2026-07-13:

- HTTP 200;
- `source=fallback`;
- `degraded=true`;
- `cached=false`;
- `summary` не пустой;
- `X-Request-ID` совпал с `request_id`;
- выполнено.

## Ручной сценарий 3: ошибка валидации

Слишком короткий или пустой `text`:

```bash
curl -i -X POST http://127.0.0.1:8000/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "", "max_sentences": 3}'
```

`max_sentences` вне диапазона:

```bash
curl -i -X POST http://127.0.0.1:8000/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Это валидный текст достаточной длины для проверки ошибки max_sentences.",
    "max_sentences": 11
  }'
```

Ожидаемый результат:

- HTTP 422;
- внешний LLM не вызывается.

Фактический результат 2026-07-13:

- пустой `text` вернул HTTP 422;
- `max_sentences=11` вернул HTTP 422;
- в логах после validation-запросов не появился новый `llm_request_started`;
- выполнено.

## Ручной сценарий 4: успешный LLM

Этот сценарий требует реального `OPENAI_API_KEY`.

Ожидаемый результат:

- HTTP 200;
- `source` равен `llm`;
- `degraded` равен `false`;
- `cached` равен `false`.

Важно:

- запрос обращается к внешнему OpenAI API;
- запрос может учитываться в биллинге;
- ключ нельзя показывать на скриншоте, в логах или в терминале.

На этапе подготовки документации этот сценарий не выполнялся.

Фактический результат 2026-07-13:

- модель: `gpt-4.1-mini`;
- HTTP 200;
- `source=llm`;
- `degraded=false`;
- `cached=false`;
- `summary` непустой, длина 294 символа;
- `X-Request-ID` совпал с `request_id`;
- выполнен один успешный реальный LLM-вызов.

## Ручной сценарий 5: cache hit

Этот сценарий имеет смысл проверять при настроенном реальном ключе, потому что fallback намеренно не кешируется.

Порядок:

1. Запустить сервис с реальным `OPENAI_API_KEY`.
2. Отправить валидный `POST /v1/summarize`.
3. Отправить второй идентичный запрос до истечения `CACHE_TTL_SECONDS`.

Ожидаемый результат:

- первый ответ: `cached=false`;
- второй ответ: `cached=true`;
- оба ответа имеют `source=llm`;
- `request_id` различаются;
- `summary` совпадают;
- в логах ожидаются события `cache_miss`, `cache_set`, затем `cache_hit`.

Без ключа этот сценарий не подтверждает кеш, потому что fallback-ответы не кешируются.

Фактический результат 2026-07-13:

- второй идентичный запрос вернул HTTP 200;
- `source=llm`;
- `degraded=false`;
- `cached=true`;
- `summary` полностью совпал с первым ответом;
- `request_id` первого и второго ответов различались;
- `X-Request-ID` второго ответа совпал с `request_id` второго JSON;
- в логах подтверждены события `cache_miss`, `llm_request_started`, `llm_response_received`, `cache_set`, `cache_hit`;
- второй запрос обслужен кешем и не потребовал нового LLM-вызова.

## GitHub Actions

Фактический результат 2026-07-13:

- push workflow для `feature/llm-summary-service`: success;
- pull_request workflow для PR #1: success;
- Python 3.9: success;
- Python 3.12: success.

## Сбой LLM

Безопасные способы проверки:

- отсутствие ключа: сервис использует configuration fallback;
- автоматический тест с fake LLM, который выбрасывает temporary error.

Не рекомендуется намеренно публиковать неверный ключ или генерировать большое количество запросов. Timeout, rate limit и provider error покрываются автоматическими тестами без реального сетевого сбоя.

## Ошибка fallback и HTTP 503

Сценарий покрывается автоматическим тестом с подменой fallback-функции. Отдельный debug endpoint для демонстрации этой ошибки не добавляется.

Ожидаемый результат при отказе fallback:

- HTTP 503;
- нейтральное сообщение `Сервис суммаризации временно недоступен.`;
- `request_id` присутствует;
- внутреннее сообщение исключения не возвращается.

## Таблица итоговой проверки

| Сценарий | Ожидаемый результат | Фактический результат | Статус |
|---|---|---|---|
| `python -m pip check` | Нет конфликтов зависимостей | `No broken requirements found.` | Выполнено |
| `python -m ruff check .` | Линтер проходит | `All checks passed!` | Выполнено |
| `python -m ruff format --check .` | Форматирование не требуется | `25 files already formatted` | Выполнено |
| `python -m pytest` | Все тесты проходят | `84 passed` | Выполнено |
| `python -m compileall app` | Модули компилируются | Успешно | Выполнено |
| `make check` | Полная локальная проверка проходит | Успешно, включая `84 passed` | Выполнено |
| Health без ключа | HTTP 200, degraded | HTTP 200, `status=degraded`, `llm_configured=false` | Выполнено |
| Fallback вручную | HTTP 200, source=fallback | HTTP 200, `source=fallback`, `degraded=true`, `cached=false`, `X-Request-ID` совпал | Выполнено |
| Ошибка валидации вручную | HTTP 422 | Пустой `text` → 422; `max_sentences=11` → 422; LLM-вызов не стартовал | Выполнено |
| Успешный LLM | HTTP 200, source=llm | HTTP 200, `source=llm`, `degraded=false`, `cached=false`, summary непустой | Выполнено |
| Cache hit с реальным LLM | Второй запрос `cached=true` | Второй идентичный запрос: `cached=true`, summary совпал, request_id различались | Выполнено |
| GitHub Actions push | Workflow success | Push workflow для feature-ветки завершился успешно | Выполнено |
| GitHub Actions pull_request | Workflow success | Pull request workflow для PR #1 завершился успешно | Выполнено |
