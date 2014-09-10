import ez_setup
ez_setup.use_setuptools()

from setuptools import setup, find_packages

setup(
    name="s4py",
    version="0.1",
    author="TQ Hirsch",
    author_email="thequux@thequux.com",
    url="http://github.com/thequux/s4py",
    packages = find_packages("lib"),
    package_dir = {'': 'lib'},
    install_requires = ['Click'],
    entry_points = {
        'console_scripts': [
            # This way, you can also use python -ms4py
            's4py=s4py.__main__:main',
        ],
    },
)
