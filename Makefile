doc:
	groff -mandoc -Thtml elogviewer.1 > html/index.html

upload-doc: doc
	rsync -avzP -e ssh html/ mathias_laurin@web.sourceforge.net:/home/project-web/elogviewer/htdocs/ 

test:
	python ./tests.py

vagrant-up:
	cd vagrant && vagrant --provision up

vagrant-destroy:
	cd vagrant && vagrant -f destroy
