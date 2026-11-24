"""Vérifie qu'un rapport respecte le contrat d'échange v1.0.

Utilisation :
    pip install jsonschema
    python valider_rapport.py report.schema.json <rapport.json>

Le même contrôle sert aux deux membres : Anthony l'utilise pour tester
les rapports produits par le Harvester, Kaïs pour le Nester (N-05).
"""
import hashlib
import json
import sys

from jsonschema import Draft202012Validator, FormatChecker


def valider(chemin_schema: str, chemin_rapport: str) -> bool:
    with open(chemin_schema, encoding="utf-8") as f:
        schema = json.load(f)
    with open(chemin_rapport, "rb") as f:
        octets = f.read()

    print(f"SHA-256 : {hashlib.sha256(octets).hexdigest()}")

    if len(octets) > 1_000_000:
        print("ÉCHEC : rapport supérieur à 1 Mo")
        return False

    try:
        rapport = json.loads(octets.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"ÉCHEC : JSON illisible ({e})")
        return False

    validateur = Draft202012Validator(schema, format_checker=FormatChecker())
    erreurs = sorted(validateur.iter_errors(rapport), key=lambda e: list(e.path))
    for e in erreurs:
        champ = ".".join(str(p) for p in e.path) or "(racine)"
        print(f"ÉCHEC : {champ} : {e.message}")

    scan = rapport.get("scan", {})
    if isinstance(scan.get("hosts"), list) and scan.get("hosts_found") != len(scan["hosts"]):
        print("ÉCHEC : scan.hosts_found ne correspond pas au nombre d'hôtes listés")
        erreurs.append("incohérence")

    if not erreurs:
        print("OK : rapport conforme au contrat v1.0")
    return not erreurs


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(0 if valider(sys.argv[1], sys.argv[2]) else 1)
