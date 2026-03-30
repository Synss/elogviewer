![Build Status](https://github.com/Synss/elogviewer/actions/workflows/python-test.yml/badge.svg?branch=main)
![Build Status](https://github.com/Synss/elogviewer/actions/workflows/ansible-test.yml/badge.svg?branch=main)
![Build Status](https://github.com/Synss/elogviewer/actions/workflows/e2e.yml/badge.svg?branch=main)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

![Gentoo](https://img.shields.io/badge/Gentoo-54487A?style=for-the-badge&logo=gentoo&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Ansible](https://img.shields.io/badge/ansible-%231A1918.svg?style=for-the-badge&logo=ansible&logoColor=white)

# An elog viewer for Gentoo

Elogviewer lets you manage [portage logs](https://wiki.gentoo.org/wiki/Portage_log)
in a Qt use interface.  It is written in Python and depends on PyQt6.


## Installation

Elogviewer is in the portage tree

    sudo emerge elogviewer

but checking the repo and the usual

    python setup.py install

should work as well provided PyQt6 is installed.


## Documentation

There is a [man page](./elogviewer.1).


## Contribution

Contributions are welcome.

Bug reports may be submitted on GitHub or [Gentoo's bugzilla](https://bugs.gentoo.org).


## Authors

Elogviewer is written by (in no particular order)

* [a17r](https://github.com/a17r)
* [Chiito](https://github.com/Chiitoo)
* Christian Faulhammer
* David Radice
* [Fonic](https://github.com/fonic)
* Jeremy Wickersheimer
* Mathias Laurin
* Timothy Kilbourn


## License

Elogviewer, copyright (c) 2007-2021, is distributed under the GPLv2 license.
