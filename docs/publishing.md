# Публикация первого релиза

## Почему нужна новая Git-история

Стабильный приватный архив, из которого подготовлен публичный пакет, содержал
runtime SQLite-базы, MAX session database, резервные копии исходников и посторонние
артефакты. Они удалены из этого каталога, но могли остаться в старой Git-истории.

Не добавляйте публичный remote к старому репозиторию. Создайте новый репозиторий из
очищенного каталога.

## Локальная проверка

```bash
python tools/check_release.py
python -m compileall -q mautrix_max vendor/pymax/src/pymax
git status --short
```

## Создание новой истории

```bash
rm -rf .git
git init -b main
git add .
git commit -m "Initial public release v0.12.0"
git tag -a v0.12.0 -m "pymatrix-max v0.12.0"
```

## Через GitHub CLI

```bash
gh auth login
gh repo create NijazKa/pymatrix-max \
  --public \
  --source=. \
  --remote=origin \
  --push

git push origin v0.12.0
```

Создайте Release из `docs/releases/v0.12.0.md`:

```bash
gh release create v0.12.0 \
  --title "pymatrix-max v0.12.0" \
  --notes-file docs/releases/v0.12.0.md
```

## Настройки GitHub

Рекомендуемые Topics:

```text
matrix max bridge mautrix python synapse element docker
```

Описание репозитория:

```text
Неофициальный многопользовательский мост Matrix ↔ MAX на Python, mautrix и PyMax.
```

Включите:

- Issues;
- Discussions — по желанию;
- Private vulnerability reporting;
- branch protection для `main`: обязательный CI и запрет force-push.
