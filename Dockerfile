# ARG keep_tree=1

FROM gentoo/stage3-amd64 as gentoo
WORKDIR /home/gentoo

# Build packages with multiple cores and set upstream USE flags.
RUN echo 'MAKEOPTS="-j8"' >> /etc/portage/make.conf \
 && echo 'FEATURES="buildpkg"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="--jobs=8"' >> /etc/portage/make.conf \
 && echo 'EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --usepkg"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} bindist -filecaps"' >> /etc/portage/make.conf \
 && echo 'USE="${USE} -llvm"' >> /etc/portage/make.conf

# Configure X.
RUN echo 'dev-libs/libpcre2 pcre16' >> /etc/portage/package.use/deps \
  && echo 'x11-libs/libxcb xkb' >> /etc/portage/package.use/deps \
  && echo 'x11-libs/libxkbcommon X' >> /etc/portage/package.use/deps \
  && echo 'x11-base/xorg-server xvfb -xorg' >> /etc/portage/package.use/deps \
  && echo 'VIDEO_CARDS="dummy"' >> /etc/portage/make.conf

# Install a recent portage tree.
ENV portage_snapshot=http://distfiles.gentoo.org/snapshots/portage-latest.tar.xz
RUN mkdir -p /var/db/repos/gentoo/ \
 && curl --silent $portage_snapshot \
  | tar -xJ --strip-components 1 -C /var/db/repos/gentoo/
RUN echo "tree installed"

# /etc/portage/make.profile -> /var/db/repos/gentoo/profiles/default/...

 # && eclean-dist
 # && [ $keep_tree -ne 1 ] && rm -rf /var/db/repos/gentoo/*

# Build minimal Xorg server.
# RUN echo 'VIDEO_CARDS="dummy"' >> /etc/portage/make.conf \
#  && echo 'x11-base/xorg-server minimal -glamor' >> /etc/portage/package.use/deps

# COPY elogviewer.py /home/gentoo/elogviewer.py
# COPY tests.py /home/gentoo/tests.py

#  && echo 'dev-python/PyQt5 gui widgets -ssl' >> /etc/portage/package.use/pyqt5 \
#  && echo 'USE="${USE} -llvm"' >> /etc/portage/make.conf
# RUN emerge x11-base/xorg-drivers
# RUN emerge xorg-server
# RUN emerge PyQt5

# Install test deps in venv with system site packages.  Note that
# we really want the system site packages because it is the whole
# point of testing in a Gentoo environment.

# RUN python3 -m venv --system-site-packages venv \
#  && . ./venv/bin/activate

# !!! use awk to find 20 with highest version in 'desktop (stable)'
# !!! or at least check that 20 is what I want (aka, a Desktop profile)
# RUN eselect profile set 20
CMD ["/bin/bash"]
