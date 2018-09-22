"""Welcome to a refactored version of Wikiextractor.

For now we have just modified the overall structure and setup.py file in order
to make wikiextractor usable as a python module
"""

import setuptools

setuptools.setup(
    name='wikiextractor',
    description='A script that extracts and cleans text from a Wikipedia'
                'database dump',
    author='Giuseppe Attardi',
    author_email='attardi@di.unipi.it',
    version='3.0',
    url='https://github.com/akb89/wikiextractor',
    license='GPL 3.0',
    keywords=['text', 'nlp'],
    packages=['wikiextractor'],
    entry_points={
        'console_scripts': [
            'wikiextractor = wikiextractor.main:main'
        ],
    },
)
