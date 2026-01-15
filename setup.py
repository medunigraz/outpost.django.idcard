#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
from setuptools import find_namespace_packages, setup

# Package meta-data
NAME = 'outpost.django.idcard'
DESCRIPTION = 'Digital employee ID cards for Apple Wallet and Google Wallet'
URL = 'https://github.com/medunigraz/ID-Card'
EMAIL = 'it@medunigraz.at'
AUTHOR = 'Medical University of Graz'
REQUIRES_PYTHON = '>=3.8.0'
VERSION = '0.1.0'

# Required packages
REQUIRED = [
    'Django>=4.2',
    'Pillow>=10.0.0',
    'qrcode[pil]>=7.4.2',
]

# Development dependencies
EXTRAS = {
    'dev': [
        'pytest',
        'pytest-django',
        'pytest-cov',
    ],
}

here = os.path.abspath(os.path.dirname(__file__))

# Load the package's __init__.py module as a dictionary.
about = {}
if not VERSION:
    with open(os.path.join(here, 'src', 'outpost', 'django', 'idcard', '__init__.py')) as f:
        exec(f.read(), about)
else:
    about['__version__'] = VERSION

# Load README
try:
    with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except FileNotFoundError:
    long_description = DESCRIPTION

setup(
    name=NAME,
    version=about['__version__'],
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    packages=find_namespace_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=REQUIRED,
    extras_require=EXTRAS,
    include_package_data=True,
    license='BSD',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Framework :: Django',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
    ],
)