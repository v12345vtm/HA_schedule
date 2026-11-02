# Changelog

## 0.0.1 - 2026-11-02

Eerste werkbare versie. Nog niet getest in een live Home Assistant-installatie.

- Datamodel v2: presets per gebruiker, weekschema per gebruiker, standaardtemperatuur per climate per weekdag.
- Presets per gebruiker met één of meer slots per climate. Slots mogen over middernacht lopen.
- Weekschema per gebruiker: een weekdag verwijst naar een preset of is leeg (null = niets gewenst, bv. verlof).
- Conflictregel: hoogste temperatuur wint, met vermelding van welke gebruikers er bij horen.
- Standaardtemperatuur per climate per weekdag. Ontbreekt die, dan wordt er niets gestuurd.
- Services: add_user, remove_user, set_preset_slot, remove_preset_slot, delete_preset, set_schedule, set_default.
- Elke mutatie wordt eerst op een kopie uitgevoerd en gevalideerd. Bij een fout blijft de data ongewijzigd.
- Sommatie-sensor per climate (`sensor.sommatie_<naam>`) met het effectieve setpoint nu en het dagverloop per weekdag.
- Temperatuur wordt begrensd op min_temp en max_temp van de climate, met een waarschuwing in het log.
- Setpoint wordt alleen verstuurd bij een wijziging, zodat een handmatige aanpassing blijft staan.
- Tester `tools/schedule_tester.py`: valideert JSON, toont het weekoverzicht, controleert een moment en heeft ingebouwde checks.

Bekende beperkingen:
- Geen GUI. Het datamodel wordt via services of direct in JSON beheerd.
- Data van de eerdere testversie (per weekdag met slots direct) wordt niet gemigreerd. Begin met een verse `.storage/climate_schedule` of verwijder die.
- De sommatie-sensor herberekent bij elke minuut het volledige week-dagverloop. Dat is prima voor een paar gebruikers, maar kan later gecachet worden.
- Geen integratie met een Home Assistant-kalender. Dat is bewust uitgesteld.
