#!/usr/bin/env python

# vi:ts=4 st=4 sw=4 et
# (c) 2010 Mathias Laurin, GPL2

class ElogviewerIdentity:
	def author(self):
		return ['Mathias Laurin <mathias_laurin@users.sourceforge.net>',
        'Timothy Kilbourn', 'Jeremy Wickersheimer',
        '',
        'contribution by',
        'Radice David, gentoo bug #187595',
        'Christian Faulhammer, gentoo bug #192701',]
	
	def documenter(self):
		return ['Christian Faulhammer <opfer@gentoo.org>']

	def artists(self):
		return ['elogviewer needs a logo, artists are welcome to\ncontribute, please contact the author.']

	def appname(self):
		return 'elogviewer'

	def version(self):
		return '0.6.2'

	def website(self):
		return 'http://sourceforge.net/projects/elogviewer'

	def copyright(self):
		'Copyright (c) 2007, 2010 Mathias Laurin'

	def license(self):
		'GNU General Public License (GPL) version 2'

	def LICENSE(self):
		return str(copyright) + '''
This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.'''

	def description(self):
		return '''
<b>Elogviewer</b> lists all elogs created during emerges of packages from Portage, the package manager of the Gentoo linux distribution.  So all warnings or informational messages generated during an update can be reviewed at one glance.

Read
<tt>man 1 elogviewer</tt>
and
<tt>man 1 /etc/make.conf</tt>
for more information.

Timothy Kilbourn (nmbrthry) has written the first version of elogviewer.
Jeremy Wickersheimer adapted elogviewer to KDE, some features he added are now imported in elogviewer.
Christian Faulhammer (V-Li) has written the man page.
'''

class FilterCommon:
    def __init__(self, label, match="", is_class=False, color='black'):
        self._name = label
        if match is "":
            self._match = label
        else:
            self._match = match
        self._is_class = is_class
        self._color = color
        self._button.set_active(True)
    
	def is_active(self):
		pass
    
    def name(self):
        return self._name
    
    def match(self):
        return self._match

    def button(self):
		pass
        
    def is_class(self):
        return self._is_class
    
    def color(self):
        return self._color


import os, fnmatch
def all_files(root, patterns='*', single_level=False, yield_folders=False):
    ''' Expand patterns for semicolon-separated strin of list '''
    patterns = patterns.split(';')
    for path, subdirs, files in os.walk(root):
        if yield_folders:
            files.extend(subdirs)
        files.sort()
        for name in files:
            for pattern in patterns:
                if fnmatch.fnmatch(name, pattern):
                    yield os.path.join(path, name)
                    break
        if single_level:
            break


import time
class Elog:
    def __init__(self, filename):
        itime = '%Y%m%d-%H%M%S.log'
        # see modules time and locale
        locale_time_fmt = '%x %X'
        sorted_time_fmt = '%Y-%m-%d %H:%M:%S'

        split_filename = filename[2:]
        split_filename = split_filename.split(':')
        t = self._category = self._package = ""
        if len(split_filename) is 3:
            (self._category, self._package, t) = split_filename
        elif len(split_filename) is 2:
            print split_filename
            (self._category, self._package) = split_filename[0].split('/')
            t = split_filename[1]
        t = time.strptime(t, itime)
        self._sorted_time = time.strftime(sorted_time_fmt, t)
        self._locale_time = time.strftime(locale_time_fmt, t)
        
        self._filename = filename
        
    def category(self):
        return self._category
        
    def package(self):
        return self._package
            
    def locale_time(self):
        return self._locale_time
        
    def sorted_time(self):
        return self._sorted_time
        
    def filename(self):
        return self._filename

	def contents(self):
		'''Parse file'''
		file_object = open(self.filename(), 'r')
		try:
			lines = file_object.read().splitlines()
		finally:
			file_object.close()
		return lines
        
    def delete(self):
        if not _debug:
            os.remove(self._filename)
        else:
            print self._filename
        return self
