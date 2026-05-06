# Eau Quotidien (Nogema) — intégration Home Assistant

Custom integration pour récupérer les données d'un compteur d'eau exposé sur la
plateforme **Eau Quotidien** de **Nogema Technology** (utilisée par Grand
Chambéry et d'autres collectivités).

## Ce que ça fait

- Login automatique avec email / mot de passe (validés à la configuration).
- Découverte automatique des compteurs accessibles au compte.
- Polling horaire (configurable via `DEFAULT_SCAN_INTERVAL` dans `const.py`).
- Re-login automatique en cas de session expirée.
- Crée un device HA par compteur, avec les entités suivantes :

| Entité | `device_class` | `state_class` | Unité | Usage |
|---|---|---|---|---|
| `sensor.compteur_xxx_index` | `water` | `total_increasing` | L | **Onglet Énergie** ✅ |
| `sensor.compteur_xxx_consumption_today` | `water` | `measurement` | L | conso du jour |
| `sensor.compteur_xxx_consumption_average` | `water` | `measurement` | L | moyenne 6 jours |
| `sensor.compteur_xxx_threshold_high` | — | — | L | seuil alerte haut (diagnostic) |
| `sensor.compteur_xxx_threshold_low` | — | — | L | seuil alerte bas (diagnostic) |

## Installation

### Manuelle

1. Copier le dossier `custom_components/eau_quotidien/` dans le répertoire
   `config/custom_components/` de votre instance Home Assistant.
2. Redémarrer Home Assistant.
3. **Paramètres → Appareils et services → Ajouter une intégration → "Eau Quotidien"**.
4. Saisir email + mot de passe. Si plusieurs compteurs sont détectés, on vous
   en propose la liste.

### Via HACS (custom repository)

1. HACS → Intégrations → menu trois points → Dépôts personnalisés.
2. Ajouter l'URL de votre fork GitHub, type "Integration".
3. Installer, redémarrer, configurer comme ci-dessus.

## Avertissements

- L'API n'est pas publique : on parse les blocs `JSON.parse('...')` embarqués
  dans le HTML de la page `/meter`. Si Nogema change son frontend, le parsing
  pourra casser — facile à corriger dans `api.py::_parse_html`.
- Vos identifiants sont stockés chiffrés dans la config entry de HA, comme
  toutes les autres intégrations.

## Configurer l'onglet Énergie

Une fois l'intégration ajoutée :

1. **Paramètres → Tableaux de bord → Énergie**.
2. Section **Eau** → Ajouter une source d'eau.
3. Choisir `sensor.compteur_xxx_index`.

Vous obtenez alors la conso journalière, mensuelle et annuelle sans aucune
configuration supplémentaire.

## Plateforme supportée

Toute installation Eau Quotidien hébergée chez Nogema. Si votre URL n'est pas
`https://eau-quotidien.xxxxx.fr`, vous pouvez la changer dans le champ
"URL de base" lors de la configuration.
