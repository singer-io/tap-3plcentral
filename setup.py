#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-tplcentral',
      version='0.0.1',
      description='Singer.io tap for extracting data from the tplcentral Mailbox API 2.0',
      author='jeff.huth@bytecode.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_tplcentral'],
      install_requires=[
          'backoff==1.8.0',
          'requests==2.20.0',
          'singer-python==5.8.0'
      ],
      entry_points='''
          [console_scripts]
          tap-tplcentral=tap_tplcentral:main
      ''',
      packages=find_packages(),
      package_data={
          'tap_tplcentral': [
              'schemas/*.json'
          ]
      })
