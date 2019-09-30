"""
Usage:
    python setup.py sdist
"""

import os
from distutils.core import setup
import elogviewer

setup(
    name="elogviewer",
    version=elogviewer.__version__,
    author="Mathias Laurin",
    author_email="Mathias.Laurin+gentoo.org@gmail.com",
    url="http://sourceforge.net/projects/elogviewer/",
    license="GPLv2",
    data_files=[("", ["elogviewer.1", "LICENSE.TXT"])],
    scripts=["elogviewer.py"],
    classifiers=os.linesep.join(
        s
        for s in """
          Development Status :: 5 - Production/Stable
          License :: OSI Approved :: GNU General Public License v2 (GPLv2)
          Programming Language :: Python :: 3
          Environment :: X11 Applications :: Qt
          """
    ),
)
