# Политика безопасности

## Поддерживаемые версии

| Версия | Поддержка |
|---|---|
| 0.12.x | ✅ |
| старше 0.12 | ❌ |

## Сообщение об уязвимости

Используйте **Private vulnerability reporting** в разделе Security репозитория.
Не публикуйте рабочий exploit, token, session database или персональные данные в
обычном issue.

Если private reporting недоступен, откройте краткий issue без чувствительных
деталей и попросите владельца организовать приватный канал.

## Что считать чувствительными данными

- `appservice.as_token` и `appservice.hs_token`;
- Matrix access token и Synapse admin token;
- MAX login token, `session.db`, `device-profile.json`;
- номер телефона и пароль 2FA;
- `data/config.yaml`, `data/registration.yaml` и база моста;
- URL MAX CDN с временной подписью;
- логи, содержащие сообщения пользователей.

## Рекомендации операторам

- запускайте мост отдельным Unix-пользователем или контейнером;
- не публикуйте порт Application Service в интернет;
- используйте отдельную Docker-сеть и firewall;
- ограничивайте `bridge.permissions` своим Matrix-доменом;
- регулярно копируйте `data/`, но храните backup как секрет;
- не запускайте две копии моста с одним session directory;
- используйте PostgreSQL для более нагруженных установок;
- включите media retention и лимиты Synapse в соответствии с вашей политикой.
