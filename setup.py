#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-3plcentral',
      version='0.0.1',
      description='Singer.io tap for extracting data from the 3plcentral Mailbox API 2.0',
      author='jeff.huth@bytecode.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_3plcentral'],
      install_requires=[
          'backoff==1.8.0',
          'requests==2.20.0',
          'singer-python==5.8.0'
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
