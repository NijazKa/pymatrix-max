# Аудит старых ghost-пользователей

При `bridge.group_messages_via_bot: true` новые участники групп не регистрируются в
Synapse как `@max_*`. Старые ghost-аккаунты могут остаться от предыдущих версий.

Инструмент `tools/max_ghost_cleanup.py` по умолчанию выполняет только dry-run.

В Docker:

```bash
docker exec -i mautrix-max python - \
  < tools/max_ghost_cleanup.py
```

Для проверки через Synapse Admin API передайте admin token через переменную среды:

```bash
docker exec \
  -e SYNAPSE_ADMIN_TOKEN='SECRET' \
  -i mautrix-max \
  python - \
  < tools/max_ghost_cleanup.py
```

Деактивировать конкретный проверенный MAX ID:

```bash
docker exec \
  -e SYNAPSE_ADMIN_TOKEN='SECRET' \
  -i mautrix-max \
  python - --max-id 123456789 --deactivate --yes \
  < tools/max_ghost_cleanup.py
```

Инструмент не изменяет SQL-базу Synapse напрямую. Он проверяет `appservice_id`,
наличие личного portal и memberships через Admin API. Исторические Matrix-события
после деактивации не удаляются.
