# Установка с Docker Compose

## 1. Требования

- Docker Engine и Docker Compose plugin;
- работающий Synapse;
- доступ к `homeserver.yaml` и возможность перезапустить Synapse;
- общая Docker-сеть между Synapse и мостом.

Узнать сети контейнера Synapse:

```bash
docker inspect matrix-synapse --format '{{json .NetworkSettings.Networks}}'
```

## 2. Подготовка проекта

```bash
git clone https://github.com/NijazKa/pymatrix-max.git
cd pymatrix-max
cp .env.example .env
mkdir -p data
cp example-config.yaml data/config.yaml
```

В `.env` укажите имя внешней сети Synapse:

```dotenv
MATRIX_DOCKER_NETWORK=matrix_default
TZ=Europe/Moscow
```

## 3. Настройка `data/config.yaml`

Минимально измените:

```yaml
homeserver:
  address: http://matrix-synapse:8008
  domain: example.org

appservice:
  address: http://mautrix-max:29320

bridge:
  permissions:
    "*": relay
    "example.org": user
    "@admin:example.org": admin
```

`homeserver.address` должен быть доступен из контейнера моста. `appservice.address`
должен быть доступен из контейнера Synapse.

## 4. Сборка

```bash
docker compose build
```

При нестабильном соединении с PyPI повторите сборку. Docker сохранит успешно
собранные слои. Не используйте `--no-cache` без необходимости.

## 5. Генерация Application Service registration

```bash
docker compose run --rm mautrix-max \
  python -m mautrix_max \
  -g \
  -c /opt/mautrix-max/data/config.yaml \
  -r /opt/mautrix-max/data/registration.yaml
```

После команды должны появиться:

- `data/config.yaml` с заполненными `as_token` и `hs_token`;
- `data/registration.yaml`.

Оба файла секретные и не должны попадать в Git.

## 6. Подключение к Synapse

Сделайте `registration.yaml` доступным контейнеру Synapse. Например, добавьте bind
mount в compose-файл Synapse:

```yaml
services:
  matrix-synapse:
    volumes:
      - /полный/путь/pymatrix-max/data/registration.yaml:/data/pymatrix-max-registration.yaml:ro
```

В `homeserver.yaml`:

```yaml
app_service_config_files:
  - /data/pymatrix-max-registration.yaml
```

Если список уже существует, добавьте новый элемент, не создавайте второй ключ
`app_service_config_files`.

Перезапустите Synapse и проверьте его лог:

```bash
docker restart matrix-synapse
docker logs --tail 100 matrix-synapse
```

## 7. Запуск моста

```bash
docker compose up -d
docker compose logs -f mautrix-max
```

Проверка импортов:

```bash
docker exec -i mautrix-max python - <<'PY'
import mautrix
import pymax
import mautrix_max

print("mautrix:", mautrix.__file__)
print("pymax:", pymax.__file__)
print("pymatrix-max:", mautrix_max.__file__)
PY
```

## 8. Первая авторизация

Откройте чат с `@maxbot:example.org` и отправьте:

```text
!max login +79991234567
```

Ответьте обычным сообщением на запрос кода, а затем пароля 2FA, если он включён.
Проверить статус:

```text
!max ping
```

## Обновление

```bash
git pull
docker compose build
docker compose up -d --force-recreate
```

Перед обновлением сохраните `data/`:

```bash
tar -czf pymatrix-max-data-$(date +%Y%m%d-%H%M%S).tar.gz data
```

Не запускайте одновременно старый и новый контейнер с одним каталогом сессий.
