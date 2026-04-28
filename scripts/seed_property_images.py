"""
Seed script: attach sample image URLs to first N properties as placeholders.
This is a no-op placeholder to illustrate the seed workflow.
"""
import asyncio
from typing import List
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (inmueblebot/..)
print("Seed script placeholder. This script would insert sample images into the DB.")
def main():
    # In a real environment, this would fetch the first 5 properties and attach image URLs.
    sample = [
        f"https://placehold.co/800x600?text=Propiedad+{i+1}" for i in range(5)
    ]
    print("Would seed: first 5 properties with images:", sample)

if __name__ == "__main__":
    main()
