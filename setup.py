#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup

setup(name='jblite',
      version='0.1',
      description='J-Ben SQLite parsing scripts',
      author='Paul Goins',
      author_email='general@vultaire.net',
      url='http://jben.vultaire.net/',
      packages=['jblite'],
      requires=['jbparse'],
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Natural Language :: English',
          'Operating System :: Microsoft :: Windows :: Windows NT/2000',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Topic :: Education',
          'Topic :: Software Development :: Libraries :: Python Modules'
          ]
      )
