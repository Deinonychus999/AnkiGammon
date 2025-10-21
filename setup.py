from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="flashgammon",
    version="0.1.0",
    author="FlashGammon Contributors",
    description="Convert eXtreme Gammon analysis into Anki flashcards",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/flashgammon",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment :: Board Games",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "genanki>=0.13.0",
        "Pillow>=10.0.0",
        "requests>=2.31.0",
        "click>=8.1.0",
        "numpy>=1.24.0",
    ],
    entry_points={
        "console_scripts": [
            "flashgammon=flashgammon.cli:main",
        ],
    },
)
