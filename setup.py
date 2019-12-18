"""Setup for the mangapy package."""

from setuptools import setup, find_packages

with open('README.md') as f:
    README = f.read()

setup(
    author="Alessandro Marzoli",
    author_email="alessandromarzoli@gmail.com",
    name='mangapy',
    license="MIT",
    description='manga downloader',
    version='0.0.1',
    long_description=README,
    url='https://github.com/alemar11/manga',
    packages=find_packages(),
    python_requires=">=3.5",
    install_requires=['aiohttp'],
    classifiers=[
        # (https://pypi.python.org/pypi?%3Aaction=list_classifiers)
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Games/Entertainment',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: End Users/Desktop',
    ],
    entry_points="""
    [console_scripts]
    mangapy = mangapy.cli:main
    """
)

# http://doc.pytest.org/en/latest/goodpractices.html