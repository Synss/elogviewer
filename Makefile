html/index.html:
	mkdir -p html
	groff -mandoc -Thtml elogviewer.1 > $@

.PHONY: upload-doc
upload-doc: doc
	rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/ 

.PHONY: test
test:
	PYTHONPATH=. pytest ./tests/test_elogviewer.py

.PHONY: vm-start
vm-start:
	cd vagrant && $(MAKE) start

.PHONY: vm-stop
vm-stop:
	cd vagrant && $(MAKE) stop

.PHONY: vm-update
vm-update:
	cd vagrant && $(MAKE) update

.PHONY: vm-destroy
vm-destroy:
	cd vagrant && $(MAKE) destroy
