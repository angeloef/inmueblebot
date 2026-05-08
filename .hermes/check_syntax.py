#!/usr/bin/env python3
"""Syntax check calendar_service.py"""
import ast
import sys

with open("app/services/calendar_service.py") as f:
    ast.parse(f.read())
print("✅ Syntax OK")
sys.exit(0)
