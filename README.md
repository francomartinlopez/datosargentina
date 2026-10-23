# Datos de Argentina

Sitio de datos públicos sobre economía y gobierno en Argentina. Cada indicador se muestra en moneda constante, con cuatro vistas: variación interanual, desde el inicio del gobierno actual, serie histórica desde mayo de 2003 y comparación entre gestiones.

## Cómo funciona

1. `indicadores.yaml` define cada serie (fuente e identificador) y cada indicador que se publica.
2. `python -m pipeline.construir` baja las series, las lleva a frecuencia mensual, arma el IPC empalmado, pasa los valores a moneda constante y calcula las vistas.
3. El resultado queda en `sitio/public/datos/` (un JSON y un CSV por indicador, más `portada.json` e `indice.json`) y el resumen de la corrida en `data/informe.md`.
4. El día 20 de cada mes GitHub Actions corre el proceso y abre un pull request con los cambios y las alertas. Al aprobarlo, se publica.

## Fuentes

| Fuente | Qué aporta |
| --- | --- |
| [API Series de Tiempo (datos.gob.ar)](https://apis.datos.gob.ar/series/api/) | INDEC, Hacienda, UTDT y otras series oficiales |
| [API del BCRA v4](https://api.bcra.gob.ar/estadisticas/v4.0/monetarias) | Reservas, tipo de cambio, base monetaria, tasas, crédito |
| [ArgentinaDatos](https://argentinadatos.com) | Dólar CCL y MEP, riesgo país |
| [FRED](https://fred.stlouisfed.org/series/CPIAUCSL) | IPC de Estados Unidos, para expresar dólares constantes |

## Metodología

- **IPC empalmado:** IPC-GBA del INDEC hasta diciembre de 2006, IPC de San Luis de 2007 a julio de 2012, IPC de la Ciudad de Buenos Aires hasta diciembre de 2016 e IPC nacional del INDEC desde entonces. Se encadenan las variaciones mensuales de cada tramo.
- **Moneda constante:** pesos deflactados con el IPC empalmado y dólares con el IPC de Estados Unidos, ambos llevados al último mes con dato.
- **Tasas y porcentajes** (desocupación, tasas de interés, riesgo país): las variaciones se expresan en puntos, no en porcentaje.
- **Comparación entre gestiones:** base 100 el mes previo a cada asunción, eje en meses desde la asunción.

## Carga manual

Las series sin descarga automática van en `data/manual/<serie>.csv` con columnas `fecha,valor,fuente_url`. Se pueden editar desde la web de GitHub.

## Uso local

```bash
pip install -r requirements.txt
python -m pytest -q
python -m pipeline.construir            # descarga y procesa
python -m pipeline.construir --offline  # reprocesa con los datos ya bajados
```
