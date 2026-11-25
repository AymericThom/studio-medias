"""Prépare le dossier à envoyer sur GitHub, SANS tes clés ni tes données.

Lance : python preparer_github.py   ->  crée le dossier « POUR_GITHUB » sur ton bureau (dossier media).
Ensuite, glisse TOUT son contenu dans ton dépôt GitHub (Add file > Upload files).
"""
import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent
DST = SRC.parent / "POUR_GITHUB"
EXCLUS = {"data", "site", "__pycache__", ".venv", ".git", ".claude"}

DST.mkdir(exist_ok=True)
for old in DST.iterdir():                    # on vide le dossier (sans le supprimer : il peut être ouvert)
    shutil.rmtree(old) if old.is_dir() else old.unlink()
shutil.copytree(SRC, DST, ignore=lambda d, noms: [n for n in noms if n in EXCLUS or n.endswith(".pyc")],
                dirs_exist_ok=True)
fichiers = [f for f in DST.rglob("*") if f.is_file()]
assert not any("settings.json" in f.name for f in fichiers), "settings.json ne doit jamais partir sur GitHub"
print(f"Prêt : {DST}  ({len(fichiers)} fichiers, sans data/ ni clés)")
