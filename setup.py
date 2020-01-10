"""Setup for the mangapy package."""

from setuptools import setup, find_packages

with open('README.md') as f:
    README = f.read()

setup(
    author="Alessandro Marzoli",
    author_email="me@alessandromarzoli.com",
    name='mangapy',
    license="MIT",
    description='Manga downloader',
    version='1.2.0',
    long_description=README,
    url='https://github.com/alemar11/mangapy',
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=['bs4', 'pillow', 'requests', 'tqdm'],
    classifiers=[
        # (https://pypi.python.org/pypi?%3Aaction=list_classifiers)
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.7',
        'Topic :: Games/Entertainment',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: End Users/Desktop',
    ],
    entry_points="""
    [console_scripts]
    mangapy = mangapy.cli:main
    """
)
