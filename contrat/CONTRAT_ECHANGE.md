# Contrat d'échange Harvester → Nester — v1.0 (brouillon)

**Projet :** Seahawks Monitoring — MSPR TPRE552
**Tâche :** T-10
**Rédacteurs :** Anthony GIANNETTO (Harvester) · Kaïs PERIDY (Nester)
**Statut :** brouillon à valider à deux — transport : **POST HTTPS** (Q3 : choix laissé libre par l'encadrant, voir section 3)

Ce document est le **seul point de jonction** entre les deux composants. Tant qu'il est respecté, chacun peut développer sa partie sans attendre l'autre. Toute modification passe par une nouvelle version (`schema_version`) validée par les deux membres.

---

## 1. Principe

1. À chaque collecte, le Harvester produit **un rapport JSON** conforme au schéma `report.schema.json`.
2. Il calcule l'**empreinte SHA-256** des octets exacts du fichier.
3. Il **dépose** le rapport au Nester avec son **token** et l'empreinte.
4. Le Nester **vérifie** (token → schéma → empreinte), **enregistre** le rapport et met à jour le **dernier contact** de la sonde.
5. Le Nester **répond** par un code qui dit au Harvester quoi faire du rapport (le supprimer de sa file d'attente ou le renvoyer plus tard).

---

## 2. Le rapport

### 2.1 Format général

| Règle | Valeur retenue |
|---|---|
| Format | JSON, encodage **UTF-8** |
| Taille maximale | **1 Mo** |
| Dates | **ISO 8601 en UTC** avec le suffixe `Z` — ex. `2026-11-24T08:45:00Z` |
| Durées | en secondes (nombre décimal) |
| Latences | en millisecondes (nombre décimal) |
| Version du format | champ `schema_version`, valeur `"1.0"` |

### 2.2 Nommage du fichier

```
report_<probe_id>_<AAAAMMJJ>T<HHMMSS>Z.json
```
Exemple : `report_harvester-sea-01_20261124T084500Z.json`

`probe_id` : minuscules, chiffres et tirets uniquement (ex. `harvester-sea-01`).

### 2.3 Champs

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `schema_version` | texte | oui | Version du contrat : `"1.0"` |
| `report_id` | UUID v4 | oui | Identifiant unique du rapport (sert à détecter les doublons) |
| `generated_at` | date UTC | oui | Date de fin de la collecte |
| `probe.probe_id` | texte | oui | Identifiant de la sonde |
| `probe.hostname` | texte | oui | Nom de la VM |
| `probe.ip` | IPv4 | oui | Adresse IP de la VM sur le LAN |
| `probe.version` | texte | oui | Version du Harvester (contenu du fichier VERSION, ex. `0.1.0`) |
| `scan.network` | CIDR | oui | Plage scannée (ex. `192.168.10.0/24`) |
| `scan.status` | `success` / `partial` / `failed` | oui | Résultat du dernier scan |
| `scan.started_at` | date UTC | oui | Début du scan |
| `scan.duration_s` | nombre ≥ 0 | oui | Durée du scan |
| `scan.hosts_found` | entier ≥ 0 | oui | **Nombre d'équipements détectés** |
| `scan.hosts[]` | liste | oui (peut être vide) | Détail par hôte : `ip`, `hostname` (ou `null`), `open_ports` (liste d'entiers) |
| `scan.error` | texte ou `null` | non | Message d'erreur si `status` ≠ `success` |
| `wan_latency.target` | texte | oui | Cible des pings (IP ou nom) |
| `wan_latency.samples` | entier ≥ 1 | oui | Nombre de pings envoyés |
| `wan_latency.avg_ms` | nombre ou `null` | oui | **Latence WAN moyenne** (`null` si aucune réponse) |
| `wan_latency.min_ms` | nombre ou `null` | oui | Latence minimale |
| `wan_latency.max_ms` | nombre ou `null` | oui | Latence maximale |
| `wan_latency.loss_pct` | 0 à 100 | oui | Pourcentage de pings perdus |

Les **5 indicateurs exigés par le cahier des charges** sont couverts : IP/nom de la VM (`probe.ip`, `probe.hostname`), nombre d'équipements (`scan.hosts_found`), résultat du dernier scan (`scan.status`), latence WAN moyenne (`wan_latency.avg_ms`), version (`probe.version`).

Règle de cohérence : `scan.hosts_found` doit être égal au nombre d'éléments de `scan.hosts`.

### 2.4 Empreinte SHA-256

L'empreinte est calculée **sur les octets exacts du fichier envoyé** et transmise **à côté** du rapport, jamais dedans (un fichier ne peut pas contenir sa propre empreinte : l'ajouter modifierait le fichier, donc l'empreinte).

Elle est transmise dans l'en-tête HTTP `X-Report-SHA256`.

Valeur : 64 caractères hexadécimaux en minuscules.

---

## 3. Transport

### 3.1 Transport retenu : POST HTTPS

L'encadrant a laissé le choix entre un envoi HTTPS et un dépôt SFTP (question Q3). Nous retenons le **POST HTTPS**.

```
POST /api/v1/reports
Host: <nester>
Authorization: Bearer <token de la sonde>
Content-Type: application/json
X-Report-SHA256: <empreinte>

<contenu du rapport JSON>
```

- Chiffrement : **TLS** (certificat de la CA du lab, vérifié par le Harvester — pas de `verify=False`).
- Délai d'attente côté Harvester : **10 secondes**.

### 3.2 Pourquoi HTTPS plutôt que SFTP

| Critère | POST HTTPS (retenu) | Dépôt SFTP (écarté) |
|---|---|---|
| **Retour au Harvester** | Réponse **immédiate** : le Harvester sait tout de suite si son rapport est accepté, refusé, ou s'il doit le renvoyer (section 5). | Le fichier est copié, mais le Harvester **ne sait pas** si le Nester l'a accepté ou rejeté ensuite. Impossible de gérer la file d'attente proprement. |
| **Contrôles** | Faits **au moment de la réception**, dans la même requête : un rapport invalide n'est jamais stocké. | Faits **après coup** par un programme qui surveille le dossier : il faut gérer les fichiers incomplets (`.part`), les dossiers `accepted/` et `rejected/`, et un service de plus. |
| **Authentification** | Un **token par sonde**, simple à générer, à stocker (haché côté Nester) et à faire tourner. | Un **compte SSH et une clé par sonde**, avec un chroot à configurer pour chacune : beaucoup plus lourd à administrer pour 32 franchises. |
| **Surface d'exposition** | Le Nester n'expose que le port **443**, déjà nécessaire pour l'application de consultation. | Il faut en plus ouvrir **SSH (22)** aux 32 sites, avec des comptes système sur le serveur. |
| **Cohérence technique** | Même pile que l'application de consultation (Nginx + TLS + Flask) : **un seul serveur** à sécuriser et à journaliser. | Ajoute OpenSSH, un service de surveillance de dossier et ses propres journaux. |
| **Tests et démonstration** | Testable en une commande avec `curl`, codes retour visibles en soutenance. | Plus difficile à montrer : le résultat n'apparaît qu'après le traitement en différé. |
| **Lien avec « dépôt de fichiers »** | Le rapport reste **un fichier JSON** produit, horodaté et conservé localement ; HTTPS n'est que le moyen de le déposer. | Correspond au sens littéral, mais sans avantage fonctionnel. |

**En résumé :** HTTPS donne au Harvester une réponse immédiate (ce qui rend la file d'attente et le mode déconnecté fiables), garde un seul point d'entrée sécurisé sur le Nester, et s'administre beaucoup plus simplement à l'échelle de 32 franchises.

**Évolution possible :** pour aller plus loin en sécurité, l'authentification par token pourra être remplacée par une authentification **mTLS** (un certificat client par sonde) sans changer le format du rapport.

---

## 4. Contrôles côté Nester (dans cet ordre)

1. **Token** valide et associé à une sonde connue.
2. **Taille** ≤ 1 Mo.
3. **JSON** lisible et conforme à `report.schema.json`.
4. `probe.probe_id` du rapport = sonde associée au token.
5. **Empreinte** SHA-256 recalculée = empreinte reçue.
6. `report_id` jamais reçu auparavant.

Chaque résultat (accepté ou rejeté) est **journalisé** avec le `probe_id`, le `report_id` et la raison.

---

## 5. Réponses du Nester (HTTPS)

Corps de réponse toujours en JSON : `{"status": "...", "report_id": "...", "error": "..."}`.

| Code | Signification | Ce que fait le Harvester |
|---|---|---|
| **201** | Rapport accepté et enregistré | Retire le rapport de la file d'attente |
| **409** | Rapport déjà reçu (même `report_id`) | Le considère comme livré, le retire de la file |
| **400** | JSON invalide, schéma non respecté ou empreinte incorrecte | Ne renvoie pas : journalise l'erreur, met le rapport de côté (`rejected/`) |
| **401** | Token absent ou invalide | Ne renvoie pas : journalise l'erreur (secret à vérifier ou à renouveler) |
| **403** | Le token ne correspond pas au `probe_id` | Ne renvoie pas : journalise l'erreur (erreur de configuration) |
| **413** | Rapport trop volumineux | Ne renvoie pas : journalise l'erreur |
| **5xx**, délai dépassé, réseau coupé | Nester indisponible | **Garde le rapport en file d'attente** et le renvoie à la collecte suivante |

Le code **409** rend le renvoi sans risque : si le Nester a bien reçu un rapport mais que la réponse s'est perdue, le Harvester peut le renvoyer sans créer de doublon.

---

## 6. File d'attente côté Harvester

- Les rapports non livrés restent dans `outbox/`.
- À chaque collecte, le Harvester renvoie d'abord les rapports en attente, du plus ancien au plus récent.
- Les rapports rejetés définitivement (400, 401, 403, 413) vont dans `rejected/` pour analyse.
- `latest.json` est toujours mis à jour localement, que l'envoi réussisse ou non (mode déconnecté).

---

## 7. État de la sonde côté Nester

- **Dernier contact** = date de réception du dernier rapport **accepté** (code 201).
- Sonde **déconnectée** si le dernier contact date de plus de **2 × l'intervalle de collecte** (intervalle proposé : 15 min, donc seuil de 30 min — à confirmer avec l'encadrant, question Q2).

---

## 8. Points en attente

| Point | Dépend de | Valeur provisoire |
|---|---|---|
| ~~HTTPS ou SFTP~~ | Q3 encadrant — **réglé** : choix libre | **HTTPS retenu** (section 3.2) |
| Cible de la latence WAN | Q1 encadrant | à définir dans la configuration |
| Intervalle de collecte et seuil de déconnexion | Q2 encadrant | 15 min / 30 min |
| Niveau de détail du scan de ports | Q7 encadrant | ports principaux |

---

## 9. Validation

| Membre | Rôle | Validé le |
|---|---|---|
| Anthony GIANNETTO | Harvester | |
| Kaïs PERIDY | Nester | |
