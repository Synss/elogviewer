doc:
	groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
	rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/ 

test:
	python ./tests.py

vm-start:
	cd vagrant && $(MAKE) start

vm-stop:
	cd vagrant && $(MAKE) stop

vm-update:
	cd vagrant && $(MAKE) update

vm-destroy:
	cd vagrant && $(MAKE) destroy
