from setuptools import setup

setup(
    name="elogviewer",
    version="3.1",
    author="Mathias Laurin",
    author_email="Mathias.Laurin+gentoo.org@gmail.com",
    url="https://github.com/Synss/elogviewer",
    license="GPLv2",
    install_requires=["PyQt5"],
    tests_require=["pytest", "isort", "black"],
    test_suite="tests",
    data_files=[("", ["elogviewer.1", "LICENSE.TXT"])],
    scripts=["elogviewer.py"],
    classifiers="\n".join(
        (
            "Development Status :: 5 - Production/Stable",
            "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
            "Programming Language :: Python :: 3",
            "Environment :: X11 Applications :: Qt",
        )
    ),
)
