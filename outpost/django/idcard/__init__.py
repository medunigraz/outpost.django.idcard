"""
Outpost namespace package.
This allows multiple 'outpost' packages to be installed and work together.
"""
__path__ = __import__('pkgutil').extend_path(__path__, __name__)
