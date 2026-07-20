"""Rend la racine du projet importable (`from src ...`) pendant les tests."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
