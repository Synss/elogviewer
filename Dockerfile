# Set `keep_tree=1` to keep the tree after emerging the packages.
# This is useful for debugging.
ARG keep_tree=0

FROM gentoo/stage3-amd64 as gentoo
WORKDIR /home/gentoo

# Configure make.conf for multiple cores and upstream and useful USE flags.
# `introspection` requires kernel sources.
RUN echo 'MAKEOPTS="-j8"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --binpkg-respect-use=y"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --jobs=8"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --quiet"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --usepkg"' >> /etc/portage/make.conf \
 && echo 'FEATURES="${FEATURES} buildpkg"' >> /etc/portage/make.conf \
 && echo 'FEATURES="${FEATURES} -sandbox"' >> /etc/portage/make.conf \
 && echo 'FEATURES="${FEATURES} -usersandbox"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} bindist"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} -introspection"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} -filecaps"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} -llvm"' >> /etc/portage/make.conf \
 && echo 'VIDEO_CARDS="dummy"' >> /etc/portage/make.conf \
 && cat /etc/portage/make.conf

# Configure packages.
RUN echo 'x11-libs/libxcb xkb' >> /etc/portage/package.use/opts \
 && echo 'x11-libs/libxkbcommon X' >> /etc/portage/package.use/opts \
 && echo 'dev-libs/libpcre2 pcre16' >> /etc/portage/package.use/opts \
 && echo 'x11-base/xorg-server -xorg' >> /etc/portage/package.use/opts \
 && echo 'x11-base/xorg-server xvfb' >> /etc/portage/package.use/opts \
 && echo 'dev-python/PyQt5 gui' >> /etc/portage/package.use/opts \
 && echo 'dev-python/PyQt5 widgets' >> /etc/portage/package.use/opts

# Install a recent portage tree.
COPY .cache/ /var/cache/
ENV portage_snapshot=http://distfiles.gentoo.org/snapshots/portage-latest.tar.xz
RUN mkdir -p /var/db/repos/gentoo/ \
 && curl --silent $portage_snapshot \
  | tar -xJ --strip-components 1 -C /var/db/repos/gentoo/ \
 && emerge x11-base/xorg-server \
 && emerge dev-python/PyQt5 \
 && emerge --autounmask-continue=y x11-misc/xvfb-run \
 && emerge app-portage/gentoolkit \
 && eclean --deep packages \
 && [ "${keep_tree}" = "0" ] && rm -rf /var/db/repos/gentoo/ || /bin/true

# In host:
#  - python setup.py sdist
#  - docker run --rm -ti gentoo
#  - docker cp dist/ gentoo:/home/gentoo/
#
# In container:
#  - venv and test

# TODO: Remove binpkgs from final image
#       No copy / no binpkgs and build everything once more.


# Make sdist on host and copy sdist here.

# Install test deps in venv with system site packages.  Note that
# we really want the system site packages because it is the whole
# point of testing in a Gentoo environment.
# RUN python3 -m venv --system-site-packages venv \
#  && . ./venv/bin/activate \
#  && pip install \
#   black \
#   coverage \
#   isort \
#   pytest-black \
#   pytest \
#   pytest-cov \
#   pytest-isort \
#  && pip freeze \

CMD ["/bin/bash"]
