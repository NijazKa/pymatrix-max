# Как помочь проекту

Спасибо за интерес к `pymatrix-max`.

## Перед началом

- для ошибок используйте bug report;
- для новых функций сначала откройте feature request;
- не публикуйте реальные номера телефонов, Matrix access token, MAX session token,
  `config.yaml`, `registration.yaml`, SQLite-базы и полный session directory.

## Среда разработки

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-build-isolation -e .
```

Проверки:

```bash
python -m compileall -q mautrix_max vendor/pymax/src/pymax
python -m pip check
python tools/check_release.py
```

## Pull request

1. Создайте отдельную ветку.
2. Делайте минимальные изменения без смешивания рефакторинга и исправления бага.
3. Добавьте диагностический лог, если проблема зависит от нестабильного MAX payload.
4. Не добавляйте polling без обсуждения: мост предпочитает событийную обработку.
5. Обновите README, CHANGELOG или docs, если меняется поведение пользователя.
6. Укажите, какие направления проверены: Matrix → MAX, MAX → Matrix, DM, группа,
   канал, текст, медиа.

## Vendored PyMax

Изменения в `vendor/pymax` должны быть изолированы и описаны в
`THIRD_PARTY_NOTICES.md`. По возможности добавьте ссылку на upstream issue или PR.

## Стиль

- Python 3.10+;
- четыре пробела;
- понятные имена и type hints для новых публичных методов;
- сообщения пользователю и документация — на русском;
- технические комментарии могут быть на русском или английском;
- в логах нельзя выводить полный token или URL с секретным query string.
