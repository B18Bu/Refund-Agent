.PHONY: check test compile frontend-build

check: compile test

compile:
	python -m compileall -q backend scripts

test:
	python -m pytest backend/tests -q

frontend-build:
	npm --prefix frontend run build
