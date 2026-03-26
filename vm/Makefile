ensure-dist:
	mkdir -p ../dist

setup-cache:
	mkdir -p .cache/binpkgs
	mkdir -p .cache/distfiles

.PHONY: test
test:
	cd roles/gentoo_base && uv run --extra vm molecule test

.PHONY: start
start: setup-cache ensure-dist
	vagrant --provision up

.PHONY: stop
stop:
	vagrant halt

.PHONY: update
update:
	vagrant provision

.PHONY: destroy
destroy:
	vagrant -f destroy
