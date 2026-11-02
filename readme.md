# HA_schedule: Climate Schedule voor Home Assistant

Custom component die per gebruiker presets met tijdsloten beheert, per weekdag een preset koppelt, en de resultaten per climate samenvoegt. Bij overlap wint de hoogste temperatuur.

Versie: **0.0.1**. Zie `changelog.md` voor wat er in deze versie zit.

## Repo-structuur

```
HA_schedule/
├── custom_components/
│   └── climate_schedule/
│       ├── __init__.py       # services, opslag, scheduler
│       ├── manifest.json     # versie staat in het veld "version"
│       ├── resolver.py       # pure logica: presets, conflicten, validatie
│       ├── sensor.py         # sommatie-sensor per climate
│       └── seed.json         # startdata, alleen als er nog geen opslag is
├── tools/
│   └── schedule_tester.py    # test het datamodel zonder Home Assistant
├── changelog.md
└── readme.md
```

JSON-bestanden kunnen geen commentaar bevatten. Daarom staan in `seed.json` de bestandsnaam en versie in het veld `_meta`, en in `manifest.json` in het veld `version`.

## Installatie

1. Kopieer `custom_components/climate_schedule` naar `config/custom_components/`.
2. Voeg toe aan `configuration.yaml`:

```yaml
climate_schedule:
  climates:
    - climate.keuken
```

3. Herstart Home Assistant. Bij de eerste start wordt `seed.json` opgeslagen in `.storage/climate_schedule`. Daarna is die opslag leidend, en de seed wordt niet meer gelezen.

Via HACS: voeg `https://github.com/v12345vtm/HA_schedule` toe als custom repository (categorie Integration). Let op: HACS verwacht de component in `custom_components/` in de repo-root, en dat klopt met deze structuur.

## Het datamodel

```json
{
  "schema_version": 2,
  "defaults": {
    "climate.keuken": {"monday": 18, "saturday": 19, "sunday": 19}
  },
  "users": {
    "eric": {
      "presets": {
        "voormiddag": {"climate.keuken": [{"start": "08:00", "end": "12:00", "temp": 25}]},
        "namiddag":   {"climate.keuken": [{"start": "14:00", "end": "16:00", "temp": 25}]}
      },
      "schedule": {
        "monday": "voormiddag",
        "tuesday": "namiddag",
        "wednesday": null
      }
    }
  }
}
```

- **presets**: per gebruiker een set benoemde presets. Een preset bevat per climate een lijst slots.
- **schedule**: per weekdag de preset die geldt, of `null` als er niets gewenst is (verlof, vrije dag).
- **defaults**: per climate per weekdag een standaardtemperatuur. Ontbreekt een dag, dan wordt er niets gestuurd en blijft de thermostaat staan.

### Regels

1. Voor elk moment bepaalt de resolver de actieve slots van alle gebruikers, op basis van hun preset voor die dag.
2. Zijn er slots actief, dan wint de hoogste temperatuur. Gebruikers met die temperatuur worden in de sensor vermeld.
3. Is er geen slot actief, dan geldt de default van die weekdag.
4. Is er ook geen default, dan wordt er niets gestuurd.
5. Een slot dat over middernacht loopt (bv. 22:00 tot 02:00) hoort bij de dag waarop het begint. Het restant geldt op de volgende dag.
6. De temperatuur wordt begrensd op `min_temp` en `max_temp` van de climate. Gudrun's 26 °C wordt dus begrensd op 25 °C als je thermostaat `max_temp: 25` heeft.

## Services

Alle services staan onder `climate_schedule.*`. Je kan ze in Developer Tools gebruiken of in scripts.

```yaml
service: climate_schedule.add_user
data:
  name: eric
---
service: climate_schedule.set_preset_slot
data:
  user: eric
  preset: voormiddag
  climate: climate.keuken
  start: "08:00"
  end: "12:00"
  temp: 25
---
service: climate_schedule.remove_preset_slot
data:
  user: eric
  preset: voormiddag
  climate: climate.keuken
  start: "08:00"
---
service: climate_schedule.delete_preset
data:
  user: eric
  preset: voormiddag
---
service: climate_schedule.set_schedule
data:
  user: eric
  weekday: monday
  preset: voormiddag        # weglaten of null = niets gewenst
---
service: climate_schedule.set_default
data:
  climate: climate.keuken
  weekday: monday
  temp: 18                  # null = geen default voor deze dag
```

Verwijderen van een gebruiker gebeurt met `remove_user`. Let op: mutaties die het datamodel ongeldig maken worden geweigerd met een foutmelding.

## Sommatie-sensor

Per climate komt er een sensor `sensor.sommatie_<naam>` met:

- de state: het effectieve setpoint op dit moment
- `bron`: `slot`, `default` of `geen`
- `gebruikers`: welke gebruikers het setpoint bepalen
- `presets_vandaag`: welke preset elke gebruiker vandaag heeft
- `vandaag`: het dagverloop van vandaag in segmenten
- `week`: het dagverloop van alle zeven dagen

Met `vandaag` of `week` kan je de toekomstige GUI-timeline al bouwen.

## Tester

Test je JSON zonder Home Assistant te starten. Dit is handig als je het datamodel met de hand bewerkt.

```bash
# seed.json valideren en het weekoverzicht tonen
python tools/schedule_tester.py

# je eigen JSON testen
python tools/schedule_tester.py /pad/naar/mijn.json

# één moment controleren
python tools/schedule_tester.py --at monday 09:30 climate.keuken

# waarschuwen als een temperatuur boven je max_temp uitkomt
python tools/schedule_tester.py --max-temp 25

# ingebouwde controles draaien
python tools/schedule_tester.py --selftest
```

Gebruik de tester na elke wijziging van de JSON. Een `FOUT in datamodel` betekent dat HA die data zou weigeren of met warnings zou opslaan.

## Debuggen in Home Assistant

- Zet in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.climate_schedule: debug
```

- Controleer `sensor.sommatie_keuken` en het attribuut `vandaag`.
- Bij een ongeldig datamodel verschijnen waarschuwingen in het log met `Climate Schedule datamodel:`.

## Bewust nog niet in deze versie

- **GUI**: de timeline met slepen komt later en gebruikt dezelfde services en het dagverloop uit de sensor.
- **HA-kalender**: bewust weggelaten, om niet extra inputs te koppelen. Een werkschema kan later als bron worden toegevoegd.
- **Migratie** van de testdata van vóór v0.0.1: niet nodig, verwijder `.storage/climate_schedule` en start opnieuw.
- **Config flow**: er is geen UI-configuratie. Alles gaat via `configuration.yaml` en services.
