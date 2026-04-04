default:
    just --list

doc:
    mkdir -p html
    groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
    rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/

test:
    uv run ruff format
    uv run ruff check --select I --fix
    uv run ruff check --fix
    uv run pytest

vm-test:
    cd roles/gentoo_base && uv run --extra vm molecule test
    cd roles/gentoo_system && uv run --extra vm molecule test

e2e:
    uv run --extra vm molecule test --scenario-name e2e

vm-start:
    vagrant --provision up

vm-stop:
    vagrant halt

vm-provision: vm-start
    vagrant provision

vm-reboot: vm-start
    ansible -i inventory gentoo -m ansible.builtin.reboot -b

vm-destroy:
    vagrant -f destroy

vm-ssh: vm-start
	vagrant ssh
