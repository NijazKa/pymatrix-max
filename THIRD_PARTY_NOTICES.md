# Сторонние компоненты

## PyMax

Каталог `vendor/pymax` содержит PyMax (`maxapi-python`) версии 2.3.1.

- исходный проект: https://github.com/MaxApiTeam/PyMax
- авторское право: Copyright (c) 2025 ink-developer
- лицензия: MIT, полный текст в `vendor/pymax/LICENSE`

Vendored-копия включается в wheel `pymatrix-max` и содержит совместимые с мостом изменения:

- числовой `messageId` в API реакций;
- обработку дополнительных типов входящих reaction frame;
- разбор нескольких форматов MAX video CDN payload;
- поддержку URL MPEG-DASH, который мост затем remux-ит через FFmpeg.

При обновлении PyMax эти изменения необходимо переносить и повторно тестировать.

## mautrix-python

Мост использует `mautrix-python` как внешний пакет. Проект распространяется по
MPL-2.0; условия лицензии и авторство см. в репозитории:
https://github.com/mautrix/python.

## FFmpeg

Docker-образ устанавливает FFmpeg из системного репозитория Debian. Лицензирование
конкретной сборки зависит от включённых компонентов дистрибутива Debian.
