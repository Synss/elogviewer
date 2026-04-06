[private]
_just := just_executable()

default:
    just --list

doc:
    mkdir -p html
    groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
    rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/

qa:
    uv run ruff format
    uv run ruff check --select I --fix
    uv run ruff check --fix

test: qa
    uv run pytest

_build-path type:
    @uv build --{{ type }} 2>&1 | perl -ne 'print $1 if /Successfully built\s+(.+)/'

@list-wheel:
    unzip -Z1 $({{ _just }} _build-path wheel)

@list-sdist:
    tar --list -f $({{ _just }} _build-path sdist)

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
