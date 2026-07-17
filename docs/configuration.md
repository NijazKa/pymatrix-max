# Конфигурация

Основной конфиг — `data/config.yaml`. Начинайте с `example-config.yaml`.

## `homeserver`

- `address` — URL Matrix Client-Server API, доступный мосту;
- `domain` — Matrix `server_name`;
- `software` — для Synapse оставьте `standard`.

## `appservice`

- `address` — URL моста, доступный Synapse;
- `hostname` и `port` — локальный HTTP listener;
- `database` — SQLite или PostgreSQL connection string;
- `id` — уникальный ID Application Service;
- `bot_username` — localpart bridge bot;
- `as_token` и `hs_token` — секреты, генерируются ключом `-g`.

Для Docker по умолчанию:

```yaml
appservice:
  database: "sqlite:///data/pymatrix-max.db"
```

Для PostgreSQL:

```yaml
appservice:
  database: "postgresql://pymatrix_max:пароль@postgres/pymatrix_max"
```

## `bridge.permissions`

Приоритет: точный MXID → домен → `*`.

```yaml
bridge:
  permissions:
    "*": relay
    "example.org": user
    "@admin:example.org": admin
```

- `relay` — доступ к relay-функциям, без собственного MAX login;
- `user` — разрешена персональная MAX-сессия;
- `admin` — пользователь моста с административным уровнем.

## Группы и каналы

```yaml
bridge:
  group_messages_via_bot: true
```

Рекомендуемое значение — `true`. Авторы групповых сообщений отображаются в тексте,
а Synapse не заполняется тысячами ghost-пользователей.

## Медиа

```yaml
bridge:
  media:
    max_size: 104857600
```

Лимит применяется к скачиванию из MAX, загрузке из Matrix и итоговому MP4 после
сборки DASH. Он должен быть согласован с лимитами Synapse и reverse proxy.

## Сессии MAX

```yaml
bridge:
  max:
    session_dir: "./data/sessions"
```

Для каждого Matrix-пользователя создаётся отдельный каталог. В нём находятся
MAX token, `device_id`, `mt_instance_id` и стабильный профиль устройства.
Каталог является секретом.

## Логирование

Для production рекомендуется `INFO`. HTTP debug-лог mautrix экранирует кириллицу
как JSON `\uXXXX`; отдельный лог `MAX→Matrix` выводит читаемый текст.

```yaml
logging:
  loggers:
    mau:
      level: INFO
    mau.as.api:
      level: INFO
    mau.portal:
      level: INFO
    aiohttp:
      level: WARNING
```

Не создавайте повторяющиеся YAML-ключи: `ruamel.yaml` завершит запуск с
`DuplicateKeyError`.
