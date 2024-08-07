"""Setup for the mangapy package."""

from setuptools import setup, find_packages

with open('README.md') as f:
    README = f.read()

setup(
    author="Alessandro Marzoli",
    author_email="alessandromarzoli@gmail.com",
    name='mangapy',
    license="MIT",
    description='Manga downloader',
    version='2.0.5',
    long_description=README,
    long_description_content_type='text/markdown',
    url='https://github.com/alemar11/mangapy',
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=['bs4', 'pillow', 'pyyaml', 'requests', 'tqdm'],
    classifiers=[
        # (https://pypi.python.org/pypi?%3Aaction=list_classifiers)
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.11',
        'Topic :: Games/Entertainment',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: End Users/Desktop',
    ],
    entry_points="""
    [console_scripts]
    mangapy = mangapy.cli:main
    """
)
