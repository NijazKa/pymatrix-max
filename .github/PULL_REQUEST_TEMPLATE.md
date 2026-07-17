## Что изменено

Опишите изменение и причину.

## Проверка

- [ ] `python -m compileall -q mautrix_max vendor/pymax/src/pymax`
- [ ] `python tools/check_release.py`
- [ ] Matrix → MAX проверено
- [ ] MAX → Matrix проверено
- [ ] DM проверен или не затрагивается
- [ ] Группы/каналы проверены или не затрагиваются
- [ ] Документация обновлена

## Безопасность

- [ ] В PR нет token, номеров, session DB, конфигов и персональных логов
