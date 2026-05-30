.PHONY: help install test doctor lint clean

help:
	@echo "iris — make targets"
	@echo "  install   bootstrap deps and run setup.sh"
	@echo "  test      run pytest"
	@echo "  doctor    run scripts/doctor.py"
	@echo "  lint      run ruff check"
	@echo "  clean     remove caches"

install:
	pip install -e ".[dev]"
	bash setup.sh

test:
	python3 -m pytest tests/ -v

doctor:
	python3 scripts/doctor.py

lint:
	ruff check scripts/ integrations/ tests/

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .coverage htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
