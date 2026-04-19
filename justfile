[private]
_just := just_executable()

default:
    @just --list

doc:
    mkdir -p html
    groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
    rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/

lint:
    uv run pre-commit run

lint-all:
    uv run pre-commit run --all-files

update-linters:
    uv run pre-commit autoupdate

update-dependencies:
    uv sync

update: update-linters update-dependencies

test:
    uv run pytest

qa: lint test

_build-path type:
    @uv build --{{ type }} 2>&1 | perl -ne 'print $1 if /Successfully built\s+(.+)/'

@list-wheel:
    unzip -Z1 $({{ _just }} _build-path wheel)

@list-sdist:
    tar --list -f $({{ _just }} _build-path sdist)

vm-test:
    cd roles/gentoo_base && uv run --group vm molecule test
    cd roles/gentoo_system && uv run --group vm molecule test

e2e:
    uv run --group vm molecule test --scenario-name e2e

vm-start:
    uv run --group vm vagrant --provision up

vm-stop:
    uv run --group vm vagrant halt

vm-provision: vm-start
    uv run --group vm vagrant provision

vm-deploy: vm-start
    uv build --wheel
    ansible-playbook -i inventory site.yml --tags deploy

vm-reboot: vm-start
    ansible -i inventory gentoo -m ansible.builtin.reboot -b

vm-destroy:
    uv run --group vm vagrant -f destroy

vm-ssh: vm-start
    vagrant ssh
