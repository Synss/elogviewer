default:
    just --list

doc:
    mkdir -p html
    groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
    rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/

test:
    uv run ruff format
    uv run ruff check --fix
    uv run pytest

vm-test:
    cd vm && just test

vm-start:
    cd vm && just start

vm-stop:
    cd vm && just stop

vm-provision:
    cd vm && just provision

vm-destroy:
    cd vm && just destroy

vm-ssh:
	cd vm && just ssh
