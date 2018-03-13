#!/usr/bin/env python
from distutils.core import setup

install_requires = [
    'wagtail>=2.0',
    'django-modeltranslation>=0.12',  # TODO: check this
]

setup(
    name='wagtail2-translation',
    version='0.2.0',
    description='Wagtail CMS 2.0 translation using django-modeltranslation.',
    long_description=(
        'TBD'
        ),
    author='',  # Tadas Dailyda
    author_email='',  # tadas@dailyda.com
    maintainer='',  # Tadas Dailyda
    maintainer_email='',  # tadas@dailyda.com
    # url='https://github.com/skirsdeda/wagtail-translation',
    url='https://github.com/danfis83/wagtail2-translation',
    packages=[
        'wagtail_translation',
        ],
    package_data={'wagtail_translation': [
        'static/wagtail_translation/js/*.js',
        'templates/wagtailadmin/pages/*.html']},
    install_requires=install_requires,
    # download_url='https://github.com/skirsdeda/wagtail-translation',
    download_url='https://github.com/danfis83/wagtail2-translation',
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Operating System :: OS Independent',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Framework :: Django',
        'License :: OSI Approved :: MIT License'],
    license='MIT')
