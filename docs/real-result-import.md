# Real Result Import Foundation

Этот boundary нужен для уже извлечённых, уже структурированных официальных
результатов по плаванию, которые должны попасть в существующий pipeline Athlete
Context.

Он не парсит документы, не просматривает сайты федераций, не crawling TYF, не
запускает OCR, не переводит текст, не выводит личность спортсмена и не выбирает
соревнования. Реальные файлы спортсменов и приватные source dumps должны
оставаться вне публичного репозитория; для будущих локальных данных используется
`data/private/`. Этот путь игнорируется Git.

## Назначение

`OfficialResultImport` описывает один структурированный внешний результат и
явную metadata источника. Import service отображает его в существующие domain
objects:

```text
OfficialResultImport
-> OfficialResultImportService.map_import()
-> Source + StructuredHistoricalResultInput
-> HistoricalResultIngestService
-> existing analytics
-> existing explanation
```

Layer 2 остаётся ответственным за нормализацию, duplicate handling, source
priority и conflict behavior. Import boundary не дублирует ingest logic и сам
не перезаписывает canonical results.

## Только структурированные данные

Import может хранить явные athlete, competition и event IDs. Optional reference
strings допустимы как внешний контекст, но этот boundary не разрешает их в IDs.
Mapping в `StructuredHistoricalResultInput` требует явные `athlete_id`,
`competition_id` и `event_id`.

Поддерживаемые поля результата ограничены значениями, которые уже принимает
существующая historical result model: swim date, distance, stroke, pool length,
official raw time, round, AQUA points, standard status, result status и
verification status.

## Verification and provenance

Import не является verification. Переданный `verification_status` копируется
без изменений в `Source` и `StructuredHistoricalResultInput`.

Переданные source type, source reference, optional source URL, source language и
capture time сохраняются в `Source`. Существующие source priority rules
по-прежнему решают, будет ли более поздний claim связан, отклонён, повышен или
помечен как conflict.

## Public/private boundary

Все committed tests и examples должны оставаться synthetic. Нельзя коммитить
реальные имена спортсменов, даты рождения, приватные сообщения, screenshots,
PDFs, source dumps, credentials, personal access tokens или `.env` files.

## Controlled local run

Для локальной проверки с реальным уже структурированным результатом пользователь
сам создаёт JSON-файл внутри ignored директории:

```text
data/private/
```

В репозитории есть только synthetic template:

```text
examples/private_result_template.json.example
```

Его можно использовать как схему-подсказку, но реальные значения должны
оставаться только в `data/private/` и не должны попадать в Git.

Локальный запуск:

```bash
.venv/bin/python examples/run_private_result.py data/private/result.json
```

Runner делает только controlled local flow:

```text
private structured JSON
-> OfficialResultImport validation
-> OfficialResultImportService mapping
-> HistoricalResultIngestService
-> HistoricalPerformanceAnalytics
-> ExplanationService
-> concise Russian summary
```

Runner не обращается к live external services, не запускает TYF integration, не
scraping, не OCR, не переводит текст и не пишет derived private data в
репозиторий. По умолчанию он печатает только минимальный русский summary:
ingest status, generated result ID, verification status, pool length, размер
локальной analytics progression и explanation note. Полный private payload,
source dump, даты рождения, raw messages и arbitrary metadata не печатаются.

## Controlled local history run

Для проверки нескольких уже структурированных результатов в одном локальном
in-memory repository пользователь создаёт private history JSON внутри
`data/private/`. В репозитории есть только synthetic template:

```text
examples/private_history_template.json.example
```

Локальный запуск:

```bash
.venv/bin/python examples/run_private_history.py data/private/history.json
```

Файл должен быть JSON object с непустым массивом `results`, где каждый элемент
валидируется как `OfficialResultImport`. Runner импортирует все элементы через
существующий Layer 2 ingest, затем использует `HistoricalPerformanceAnalytics`
для группировки по дисциплинам и `ExplanationService` для русских итогов.

Отчёт не печатает полный private payload, source dumps или произвольные
персональные metadata. Внешние сервисы, crawling, OCR, перевод, база данных и
запись derived private data в репозиторий не используются.
