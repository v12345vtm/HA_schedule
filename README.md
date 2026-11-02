# HA_schedule: Climate Schedule voor Home Assistant

Custom component die per gebruiker presets met tijdsloten beheert, per weekdag een preset koppelt, en de resultaten per climate samenvoegt. Bij overlap wint de hoogste temperatuur.

Versie: **0.0.3**. Zie `changelog.md` voor wat er per versie veranderde.

## Repo-structuur

```
HA_schedule/
├── custom_components/
│   └── climate_schedule/
│       ├── __init__.py       # services, opslag, scheduler
│       ├── config_flow.py    # climate picker (installatie en opties)
│       ├── const.py          # constanten
│       ├── manifest.json     # versie in het veld "version"
│       ├── resolver.py       # pure logica: presets, conflicten, validatie
│       ├── sensor.py         # sommatie-sensor per gekozen climate
│       ├── switch.py         # hoofdschakelaar testmodus
│       ├── seed.json         # startdata, alleen als er nog geen opslag is
│       ├── strings.json      # bronteksten van de UI
│       └── translations/
│           ├── en.json
│           └── nl.json
├── tools/
│   └── schedule_tester.py    # test het datamodel zonder Home Assistant
├── changelog.md
└── README.md
```

JSON-bestanden kunnen geen commentaar bevatten. Daarom staan in `seed.json` de bestandsnaam en versie in het veld `_meta`, en in `manifest.json` het versienummer in het veld `version`.

## Installatie

1. Kopieer `custom_components/climate_schedule` naar `config/custom_components/`.
2. Herstart Home Assistant.
3. Ga naar **Instellingen → Apparaten en diensten → Integratie toevoegen** en zoek **Climate Schedule**.
4. Kies in de climate picker de climates die je wilt beheren, bv. `climate.keuken`.

Via HACS: voeg `https://github.com/v12345vtm/HA_schedule` toe als custom repository (categorie Integration).

Er is geen `configuration.yaml`-configuratie meer nodig.

## Climates aanpassen

Ga naar **Instellingen → Apparaten en diensten → Climate Schedule → Configureren**. Daar voeg je climates toe of verwijder je ze. Na opslaan wordt de integratie opnieuw geladen en komen er sensoren bij of vallen er weg. Gegevens in het schema blijven bewaard.

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
- **defaults**: per climate per weekdag een standaardtemperatuur. Ontbreekt een dag, dan wordt er niets gestuurd.

### Regels

1. Voor elk moment bepaalt de resolver de actieve slots van alle gebruikers, op basis van hun preset voor die dag.
2. Zijn er slots actief, dan wint de hoogste temperatuur. De gebruikers met die temperatuur worden in de sensor vermeld.
3. Is er geen slot actief, dan geldt de default van die weekdag.
4. Is er ook geen default, dan wordt er niets gestuurd.
5. Een slot dat over middernacht loopt (bv. 22:00 tot 02:00) hoort bij de dag waarop het begint. Het restant geldt op de volgende dag.

### Temperatuurgrenzen

De integratie begrenst de temperatuur niet zelf. Vraagt een gebruiker 26 °C en heeft de climate `max_temp: 25`, dan weigert de climate de waarde. De integratie logt dan een fout met de climate en de gevraagde waarde. Zorg dus ddat de `max_temp` en `min_temp` van je climate passen bij de presets. De tester kan dit vooraf controleren met `--max-temp`.

## Services

Alle services staan onder `climate_schedule.*`. Gebruik ze in Developer Tools of in scripts.

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
  temp: 18                  # weglaten of null = geen default voor deze dag
```

Met `remove_user` verwijder je een gebruiker. Mutaties die het datamodel ongeldig maken worden geweigerd met een foutmelding, en de data blijft dan ongewijzigd.

## Sommatie-sensor

Per gekozen climate komt er een sensor `sensor.sommatie_<naam>` met:

- de state: het effectieve setpoint op dit moment
- `bron`: `slot`, `default` of `geen`
- `gebruikers`: welke gebruikers het setpoint bepalen
- `presets_vandaag`: welke preset elke gebruiker vandaag heeft
- `vandaag`: het dagverloop van vandaag in segmenten
- `week`: het dagverloop van alle zeven dagen

## Tester

Test je JSON zonder Home Assistant te starten. Handig als je het datamodel met de hand bewerkt.

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

Een `FOUT in datamodel` betekent dat de data fouten bevat. Los die op voordat je de integratie gebruikt.

## Debuggen in Home Assistant

Zet in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.climate_schedule: debug
```

- Controleer `sensor.sommatie_keuken` en het attribuut `vandaag`.
- Datamodelfouten verschijnen in het log met `Climate Schedule datamodel:`.
- Een geweigerde temperatuur verschijnt als fout met `niet ingesteld, de climate weigerde de waarde`.

## Testmodus (hoofdschakelaar)

De entity `switch.climate_schedule_testmodus` is de hoofdschakelaar.

- **Aan (testmodus):** alles wordt berekend, de sensoren werken normaal, maar er wordt **niets** naar de climates gestuurd. Elke wijziging van het gewenste setpoint wordt gelogd als `TESTMODUS ... zou op X°C gaan`. De thermostaat blijft op zijn laatste stand staan.
- **Uit:** de integratie stuurt weer en zet direct de huidige gewenste stand.

Bij een nieuwe installatie staat de testmodus **aan**. De stand wordt bewaard, ook na een herstart. In de sensor staat het attribuut `testmodus`.

Om de testlogs te zien, zet in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.climate_schedule: info
```

## Bewust nog niet in deze versie

- **GUI**: de timeline met slepen komt later en gebruikt dezelfde services en het dagverloop uit de sensor.
- **HA-kalender**: bewust weggelaten, om niet extra inputs te koppelen.
- **Migratie** van testdata van vóór 0.0.1: verwijder `.storage/climate_schedule` en start opnieuw.

---

made by: https://claude.ai/chat/ee75c650-528d-4ff8-928c-954cc029347f
