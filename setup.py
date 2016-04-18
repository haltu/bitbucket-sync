from setuptools import setup

setup(
    name='bbsync',
    version='0.1',
    py_modules=['bbsync'],
    install_requires=[
        'click==3.3',
        'requests==2.5.0',
    ],
    entry_points='''
        [console_scripts]
        bbsync=bbsync:cli
    ''',
)
