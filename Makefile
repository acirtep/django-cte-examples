.PHONY: install run

install:
	uv sync

run:
	cd django_cte_examples && \
	uv run manage.py migrate && \
	uv run manage.py initial_load && \
	DJANGO_SUPERUSER_PASSWORD=admin uv run manage.py createsuperuser --username admin --email admin@admin.admin --noinput || true && \
	uv run manage.py runserver
