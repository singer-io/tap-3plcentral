#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-3plcentral',
      version='1.0.2',
      description='Singer.io tap for extracting data from the 3PLCentral Resource (REL) API.',
      author='jeff.huth@bytecode.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_3plcentral'],
      install_requires=[
          'backoff==2.2.1',
          'requests==2.32.5',
          'singer-python==6.1.1'
      ],
      entry_points='''
          [console_scripts]
          tap-3plcentral=tap_3plcentral:main
      ''',
      packages=find_packages(),
      package_data={
          'tap_3plcentral': [
              'schemas/*.json'
          ]
      })