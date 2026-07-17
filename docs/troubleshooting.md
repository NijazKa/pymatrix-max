# Диагностика

## `ModuleNotFoundError: No module named 'mautrix'`

Образ был собран с `pip install --no-deps`, но базовый образ не содержал mautrix.
Используйте штатный `Dockerfile` и не отключайте runtime-зависимости.

## Таймаут `files.pythonhosted.org`

Это сетевая ошибка, не ошибка исходного кода. Повторите `docker compose build` без
`--no-cache`. Успешные слои останутся в кэше.

## `DuplicateKeyError` в `config.yaml`

В YAML повторяется ключ, например два блока `mau:` или `bridge:`. Объедините их в
один блок.

## `FAIL_LOGIN_TOKEN`

MAX отозвал сохранённый token. Мост уведомит management-комнату. Выполните новый
`!max login`. Диагностический лог содержит только SHA-256 fingerprint token, но не
сам token.

## `chat.exit.not.active.user`

Аккаунт уже не состоит в MAX-чате. Современная версия моста считает это успешной
локальной очисткой. Проверьте, что `portal_user` для аккаунта удалён.

## Приглашение в групповую Matrix-комнату не приходит

В management-комнате конкретного пользователя:

```text
!max syncgroups <MAX chat_id>
```

или:

```text
!max syncgroups !matrixRoomId:example.org
```

## В Synapse появились тысячи `@max_*`

Включите:

```yaml
bridge:
  group_messages_via_bot: true
```

Новые участники групп не будут регистрироваться как ghost. Для аудита старых
аккаунтов используйте `tools/max_ghost_cleanup.py`. По умолчанию он работает в
режиме dry-run.

## Видео приходит, но не воспроизводится

Проверьте наличие FFmpeg:

```bash
docker exec mautrix-max ffmpeg -version | head -1
```

В логе должны быть `application/dash+xml` и `MAX DASH video remuxed`. Согласуйте
`bridge.media.max_size` с лимитом Synapse.

## Реакция из MAX не появляется в Matrix

Известное ограничение: MAX-клиент может не прислать reaction push frame. Постоянный
polling намеренно не используется, чтобы не создавать нагрузку.
