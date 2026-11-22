# ClaudeMisc

Claudes eget arbeidsområde: små prosjekter, eksperimenter, verktøy og notater
som skal leve lenger enn én økt.

## Struktur

| Mappe / fil        | Innhold                                                    |
| ------------------ | ---------------------------------------------------------- |
| `projects/<navn>/` | Selvstendige prosjekter, én mappe hver, med egen README    |
| `tools/`           | Hjelpeskript for arbeid i repoet                           |
| `notes/log.md`     | Logg over økter, nyeste først                              |
| `CLAUDE.md`        | Konvensjoner og erfaringer som Claude leser ved oppstart   |
| `scratch/`         | Lokal kladd, ignoreres av git                              |

## Nytt prosjekt

```bash
tools/new-project.sh mitt-prosjekt
```

Lager `projects/mitt-prosjekt/README.md` med en mal for hva prosjektet er, hvordan
det kjøres og hvilken status det har.

## Prosjekter

| Prosjekt | Hva | Status |
| --- | --- | --- |
| [poe1-build-helper](projects/poe1-build-helper/) | Analyse av Path of Exile 1-builds fra PoB-koder: oppsummering, trade-søk etter oppgraderinger, sammenligning med andres builds | under arbeid |
