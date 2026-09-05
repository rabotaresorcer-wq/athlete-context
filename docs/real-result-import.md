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
