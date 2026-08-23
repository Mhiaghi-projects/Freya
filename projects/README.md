# Backlog de Freya

Un fichero YAML por proyecto. Cada proyecto es un servicio. Estos ficheros son
la **semilla** de `project-manager`: en la Fase 6 se cargan en la base de datos
y a partir de ahí el backlog vive dentro de Freya. Hasta entonces, estos
ficheros son la fuente de verdad.

## Escala de dificultad

| Nivel | Nombre | Esfuerzo | Descripción | XP |
|---|---|---|---|---|
| 1 | Trivial | < 1 h | Configuración, un fichero, sin decisiones | 10 |
| 2 | Fácil | 1–3 h | Patrón conocido, camino claro | 25 |
| 3 | Media | 3–8 h | Varias piezas, alguna decisión de diseño | 60 |
| 4 | Alta | 1–3 días | Diseño no obvio, casos borde, integración | 150 |
| 5 | Muy alta | > 3 días | Investigación, riesgo real, puede fallar | 400 |

La dificultad del **proyecto** no es la suma de sus tasks: refleja la dificultad
intrínseca del dominio y el riesgo de equivocarse en el diseño.

## Esquema de un fichero de proyecto

```yaml
id: storage
name: Storage
phase: 4
difficulty: 4
depends_on: [auth, gestor-db]
description: ...
tasks:
  - id: storage-01
    title: ...
    difficulty: 3
    depends_on: [storage-00]     # opcional
    acceptance: ...              # cómo se sabe que está hecha
```

## Estado global

| Proyecto | Fase | Dificultad | Tasks | XP total |
|---|---|---|---|---|
| fundaciones | 0 | 3 | 7 | 315 |
| database | 1 | 2 | 4 | 170 |
| gestor-db | 1 | 4 | 8 | 665 |
| auth | 2 | 5 | 9 | 795 |
| secrets | 3 | 5 | 7 | 1120 |
| storage | 4 | 4 | 8 | 590 |
| git | 5 | 5 | 8 | 1895 |
| project-manager | 6 | 3 | 8 | 375 |
| gestor-monitoring | 7 | 3 | 7 | 530 |
| cicd | 8 | 5 | 8 | 1215 |
| frontend | 9 | 4 | 9 | 810 |
| gamification | 10 | 3 | 9 | 595 |
| **Total** | | | **92** | **9 075** |

Cifras generadas por `infra/scripts/backlog_stats.py`. Si cambias un YAML,
vuelve a ejecutarlo antes de dar la task por cerrada.
