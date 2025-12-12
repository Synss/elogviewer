html/index.html:
	mkdir -p html
	groff -mandoc -Thtml elogviewer.1 > $@

.PHONY: upload-doc
upload-doc: doc
	rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/ 

.venv:
	uv venv
	uv pip install -r pyproject.toml --all-extras

.PHONY: test
test: .venv
	uv run ruff format
	uv run ruff check --fix
	uv run pytest

.PHONY: vm-start
vm-start:
	cd vm && $(MAKE) start

.PHONY: vm-stop
vm-stop:
	cd vm && $(MAKE) stop

.PHONY: vm-update
vm-update:
	cd vm && $(MAKE) update

.PHONY: vm-destroy
vm-destroy:
	cd vm && $(MAKE) destroy
