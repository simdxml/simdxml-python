.PHONY: dev release test lint typecheck clean

dev:
	uv run --group dev maturin develop --uv

release:
	uv run --group dev maturin develop --release --uv

test: dev
	uv run --group test pytest tests/ -v

lint:
	uv run --group lint ruff check .
	uv run --group lint ruff format --check .

typecheck:
	uv run --group lint pyright

format:
	uv run --group lint ruff format .
	uv run --group lint ruff check --fix .

clean:
	cargo clean
	rm -rf target/ dist/ *.egg-info
