#!/usr/bin/env python3
"""Prints migration SQL to run in Supabase SQL Editor."""
from pathlib import Path

sql_path = Path(__file__).parent.parent / "src/vgv_rag/storage/migrations/001_initial_schema.sql"
print("Run the following SQL in the Supabase Dashboard > SQL Editor:\n")
print(sql_path.read_text())
