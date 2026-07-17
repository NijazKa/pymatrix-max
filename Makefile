.PHONY: check compile secret-check docker-build

check: compile secret-check

compile:
	python -m compileall -q mautrix_max vendor/pymax/src/pymax

secret-check:
	python tools/check_release.py

docker-build:
	docker compose build
