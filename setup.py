#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-3plcentral',
      version='0.0.4',
      description='Singer.io tap for extracting data from the 3PLCentral Resource (REL) API.',
      author='jeff.huth@bytecode.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_3plcentral'],
      install_requires=[
          'backoff==1.8.0',
          'requests==2.22.0',
          'singer-python==5.8.1'
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
