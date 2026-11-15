# Revisión manual de las 100 consultas candidatas

Fichero revisado: `data/queries_candidates.jsonl`.

**Cómo se hizo:** Claude hizo una primera revisión de las 100 consultas, con el motivo de cada descarte. Después el grupo revisó a mano muchas de ellas.

**Resultado:** 35 consultas descartadas (`"discard": true`) y **65 conservadas**. No se ha modificado ninguna consulta (`query`) ni ninguna métrica; el único campo cambiado es `discard`.

| Tipo | Conservadas | Descartadas |
|---|---|---|
| `busqueda` | 16 | 4 |
| `ingredientes` | 12 | 8 |
| `duda` | 12 | 8 |
| `restriccion` | 14 | 6 |
| `compra` | 11 | 9 |
| **Total** | **65** | **35** |

## Criterios

Cada consulta se leyó junto al texto completo de su receta en `data/processed/chunks.jsonl`. La evaluación es *known-item*: cada consulta tiene **una sola receta relevante**, y Recall@K y MRR penalizan cualquier otra receta que el sistema ponga por delante. Por eso una consulta solo sirve si esa receta es **la única respuesta correcta**.

Se descarta una consulta cuando:

- **A. Ambigua:** otras recetas de la colección cumplen todo lo que pide la consulta igual de bien que la receta objetivo, y la consulta no menciona lo que la distingue. Un sistema que devolviera esas otras recetas estaría acertando, pero la métrica lo contaría como fallo. Para no descartar por intuición, se buscaron en las 17.505 recetas las que contienen todos los rasgos de la consulta y se leyeron las coincidencias. En cada caso se citan las recetas que compiten.
- **B. Sin respuesta en la receta:** una consulta de tipo `duda` que pregunta un dato que la receta no contiene.

**No** se descarta por solapamiento alto ni por copia literal por sí solos. Los avisos (`flags`) son orientativos (ver README) y en las consultas de `busqueda` es normal nombrar el plato. Se conservan si la consulta identifica una única receta (ver la última sección).

Tampoco se descarta cuando una receta parecida tiene ingredientes llamativos que la consulta no menciona. Por ejemplo, en q085 «Cóctel de gambas con aguacate y gajos de naranja» lleva aguacate y naranja, y alguien que buscara esa receta los nombraría.

## Consultas descartadas (35)

| qid | Tipo | Consulta | Criterio | Motivo |
|---|---|---|---|---|
| q001 | restriccion | busco un relleno de carne molida con pasas y huevo duro para empanadas | A | Otras 6 recetas llevan carne molida, pasas y huevo duro para empanadas: «Relleno para empanadas de carne», «Empanada Chilena», «Empanadas argentinas de carne picada», «Empanadas criollas de carne», etc. Lo propio de esta (cerdo, zanahoria, ají) no aparece. |
| q003 | duda | ¿cuánto tiempo hay que hornear las pepas rellenas de dulce para que queden crujientes? | A | Hay 7 recetas de pepas, todas rellenas de dulce y horneadas. No menciona lo que distingue esta (harina de arroz, sin gluten); «Pepas sin TACC» respondería igual. |
| q008 | busqueda | albóndigas rellenas de queso en salsa de chipotle | A | «Albóndigas rellenas de queso» (otra receta) es justo eso: albóndigas rellenas de queso en salsa de chipotle. Encaja mejor que la receta objetivo, cuyo rasgo propio (el arroz) no aparece. |
| q009 | compra | ¿qué necesito comprar para hacer un brownie húmedo con canela y cobertura de chocolate? | A | «Brownie tradicional» también lleva canela y cobertura de chocolate. |
| q010 | ingredientes | ¿Qué antojito mexicano puedo hacer con tortilla de maíz, pollo cocido y crema para una cena? | A | 30 recetas llevan tortilla de maíz, pollo y crema: flautas, enchiladas, tacos, etc. Entre ellas «Flautas de pollo y queso». |
| q012 | ingredientes | ¿Qué plato puedo preparar con arroz, tocino picado y cebolla para un almuerzo reconfortante? | A | 24 recetas de arroz llevan tocino o bacon y cebolla: arroz paisa, «Arroz con maíz y tocineta», «Arroz navideño con pasas y tocino», etc. |
| q015 | compra | ¿qué ingredientes necesito para hacer un pastel de capas con berenjena horneada y relleno de jamón? | A | «Pastel de berenjenas al horno» y «Pastel de berenjenas con jamón y queso» también son pasteles de berenjena en capas con jamón. Lo propio de esta (puerro, huevo) no aparece. |
| q017 | duda | ¿Cuánto tiempo debe reposar esta ensalada con pollo, mandarina y queso antes de servir? | B | La receta no habla de reposo: solo dice «mezclar todos los ingredientes y agregar la vinagreta». |
| q020 | busqueda | pico de gallo fresco con mucho cilantro y trozos de tomate | A | Hay 9 recetas de pico de gallo y la consulta describe el clásico (tomate y cilantro), sin nada que distinga esta. |
| q032 | restriccion | busco un postre cremoso de huevo y vainilla cocinado en microondas con caramelo | A | 9 flanes llevan huevo, vainilla, caramelo y microondas: «Flan de huevo en microondas», «Flan en 10 minutos», «Flan de queso al microondas», etc. |
| q034 | duda | ¿A qué temperatura horneo las tapitas de masa quebrada para que queden levemente doradas? | A | No nombra el plato (alfajores) ni sus rasgos (avena, coco). «Tapitas de masa quebrada» vale para cualquiera de las 16 recetas de alfajores. |
| q040 | restriccion | busco una galleta crujiente de almendra y limón hecha con cabello de ángel | A | «Delicias cordiales» es la misma galleta: almendra, limón y cabello de ángel. |
| q045 | ingredientes | ¿qué plato puedo hacer con pechuga, jamón de York y queso para un relleno enrollado? | A | «Enrollado de pollo con jamón» y «Cordon Blue» también son pechuga enrollada con jamón y queso. |
| q046 | compra | ¿qué ingredientes necesito para hacer la torre fría de panqueques con huevo duro y mayonesa? | A | «Torre de panqueques vegetariana» también es una torre fría de panqueques con huevo duro y mayonesa. Lo propio de esta (jamón, queso) no aparece. |
| q047 | duda | ¿Cuánto tiempo hay que cocer la escarola en aceite antes de añadir los huevos? | A | «Tortilla de ESCAROLA Mº Carme Roca» es **la misma receta con el mismo texto**: es un duplicado que la deduplicación por (`ingredients`, `steps`) no eliminó. Cualquier sistema empata entre las dos. |
| q051 | restriccion | busco un plato casero de arroz con albóndigas jugosas que lleve salsa de tomate y laurel | A | «Albóndigas de pescado con arroz» es la misma receta con mero en lugar de carne (mismos pasos, tomate y laurel), y la consulta no dice de qué son las albóndigas. |
| q055 | compra | ¿qué ingredientes necesito para hacer un flan cremoso con canela y vainilla para cuatro personas? | A | «Flan De Vainilla Con Canela» y «Flan de huevo en microondas» encajan igual. Lo propio de esta (queso crema, maicena) no aparece. |
| q056 | duda | ¿cuánto tiempo debo dejar remojando la pulpa de tamarindo antes de licuarla? | A | No nombra el jugo ni la piña. «Pulpa de tamarindo» (otra receta) explica precisamente el remojo, con otro tiempo (30 min frente a 15 min aquí), así que la pregunta tiene dos respuestas distintas. |
| q061 | busqueda | arepa venezolana rellena de queso hecha en plancha | A | «Arepas Rellenas de Queso» y «Arepas de Queso» también son arepas de harina precocida rellenas de queso y hechas en sartén. Solo «venezolana» las separa (hay 34 recetas de arepas). |
| q064 | duda | ¿cómo preparo los frijoles con chile adobado y chorizo al final? | A | «Frijoles Puercos a la chipotle» es lo mismo: frijoles molidos con chorizo y chile chipotle (adobado). |
| q070 | compra | ¿qué ingredientes necesito para hacer un plato de anchoas salteadas en sidra con cebolla y ajo? | A | «Boquerones a la sidra con ensalada de patata» también lleva boquerón (= anchoa) en sidra con cebolleta y ajo. |
| q071 | duda | ¿Cuánto tiempo hay que cocinar el calabacín y la cebolla para que queden bien blanditos en el pisto? | A + B | La receta no da tiempos («hasta que estén blanditos»). Además, la consulta solo habla del pisto, sin gambas ni hojaldre, y hay 28 recetas con pisto. |
| q076 | restriccion | busco camarones salteados en mantequilla con cebolla, ajo y salsa de tomate | A | No menciona la salsa catsup, que es lo que distingue la receta. «Camarones a la diabla», «Camarones al chipotle» y otras 3 también saltean camarones en mantequilla con cebolla, ajo y tomate. |
| q078 | compra | ¿qué ingredientes necesito para hacer un guiso con pescado blanco y mariscos al estilo mediterráneo? | A | Encaja con unas 12 recetas: zarzuela, cazuelas de mariscos, «Merluza a la cazuela con almejas», etc. Además, «estilo mediterráneo» no está en la receta (es chilena, con reineta y salsa blanca). |
| q080 | ingredientes | ¿Qué plato puedo preparar con romeritos, mole y nopales para una comida familiar? | A | Las 4 recetas de romeritos llevan mole y nopales. Lo propio de esta (el huevo) no aparece. |
| q081 | compra | ¿qué ingredientes necesito para hacer las patatas gratinadas con queso fundido y salsa cremosa? | A | 18 recetas de patatas o papas gratinadas con queso y crema. |
| q082 | ingredientes | ¿Qué postre puedo hacer con claras de huevo, azúcar y zumo de limón para decorar? | A | Describe un merengue y hay unas 40 recetas de merengue, entre ellas «Merengue para decorar» (claras y azúcar, para decorar) y «Nevado de limón». |
| q083 | busqueda | caldillo de pescado con papas julianas y pimentón rojo | A | «Caldillo de congrio (¡Receta Chilena Fácil!)» y «Caldillo de congrio» también llevan pescado, papas en tiras y pimentón. |
| q089 | ingredientes | ¿Qué puedo hacer con una bolsa de gelatina y agua para un postre refrescante? | A | 126 recetas llevan gelatina, y «gelatina y agua» describe cualquiera. |
| q091 | restriccion | busco un flan suave hecho al vapor en olla exprés que use leches condensada y evaporada | A | «Flan de tres leches en olla express» y «Flan napolitano en olla express» también son flanes en olla exprés con leche condensada y evaporada. |
| q092 | compra | ¿qué ingredientes necesito para hacer estos bollos crujientes con mucho queso fundido para seis personas? | A | «Bollos crujientes con queso» no nombra los buñuelos ni el gruyere: encaja con pan de queso, bolitas de queso, croquetas, etc. (unas 49 recetas). Además, «crujientes» no aparece en la receta. |
| q094 | ingredientes | ¿Qué puedo preparar con carne molida, papas y leche para un plato reconfortante tipo pastel? | A | 13 pasteles de carne y papa: «Pastel de patata y carne picada», «Pastel de carne en puré de papas…», «Pastel de carne al horno», etc. |
| q097 | duda | ¿Cuánto tiempo debo hervir la leche con azúcar y canela antes de añadir el aguardiente? | A + B | La «Cola de mono» (2 recetas) y el sabajón también hierven leche con azúcar y canela y llevan aguardiente u otro licor. Además, la receta no da un tiempo de hervor. |
| q098 | compra | ¿qué ingredientes necesito para preparar unas milanesas crujientes de cerdo o vaca con huevo y hierbas? | A | 14 milanesas de carne llevan huevo y hierbas. No menciona lo propio de esta (rebozado solo con harina, «marineras»). |
| q100 | ingredientes | ¿Qué batido puedo preparar con remolacha, zanahoria y apio para desayunar? | A | «Batido de remolacha, zanahoria y manzana» también lleva remolacha, zanahoria y apio, y también es para el desayuno. |

## Consultas con aviso que se conservan (23)

Todas identifican una única receta en la colección. El aviso se explica porque nombran el plato, que es normal en `busqueda`, o porque copian una expresión culinaria común.

| qid | Aviso | Por qué se conserva |
|---|---|---|
| q005 | solapamiento_alto | Criadillas, sesos, vino blanco y «babosa» solo coinciden aquí. La otra «Tortilla sacromonte» no lleva vino y sí patata, jamón y chorizo. |
| q014 | longitud, solapamiento_alto | Es la única tortilla de acelgas al horno. Parafrasea el título («horneada», «ligera»). |
| q018 | copia_literal | La copia es «claras a punto de nieve», una expresión culinaria genérica. Es el único postre de chocolate con edulcorante y claras. |
| q028 | solapamiento_alto, copia_literal | Nombra el plato (`busqueda`), y el relleno de rúcula, champiñones y hummus es único. |
| q035 | copia_literal | «Lomos de merluza al ajillo» es el nombre del plato. Solo hay otra receta de merluza con guindilla (cocochas en salsa verde). |
| q039 | solapamiento_alto | Es la única pulpeta. Pregunta un dato que está en la receta (40 min). |
| q041 | solapamiento_alto, copia_literal | Es la única receta de rollitos tailandeses. |
| q043 | solapamiento_alto | «Compota de manzana para Navidad» también lleva canela y naranja, pero sobre todo higos, ciruelas y licor, que la consulta no menciona. «Dorada» apunta a la manzana Golden de esta. |
| q050 | solapamiento_alto | Es la única tortilla de bacalao con guindilla y de estilo vasco. |
| q052 | solapamiento_alto | La receta solo tiene esos tres ingredientes. «Yogur helado con sabor a cacao» lleva cacao, que la consulta no menciona. |
| q053 | copia_literal | Nombra el plato (`busqueda`). Es la única torta de pera con azúcar glas. |
| q057 | solapamiento_alto | Es la única receta de ojos de gelatina para Halloween. |
| q059 | longitud, solapamiento_alto | Es la única caldereta con panga. |
| q060 | solapamiento_alto | Es la única copa de langostinos con ensaladilla. |
| q067 | solapamiento_alto | Hay otros budines de mandarina, pero solo este lleva bizcochos remojados en leche y licor. |
| q074 | solapamiento_alto | Es la única lubina al horno con laurel y limón. |
| q077 | solapamiento_alto | Es la única quiche con tomate frito en dados. Pregunta un dato que está en la receta (20 min). |
| q079 | solapamiento_alto | Es la única receta de atún con vinagre de Jerez. |
| q084 | copia_literal | Nombra el plato. Pregunta un dato que está en la receta (aceite muy caliente, 2-3 min por lado). |
| q086 | solapamiento_alto | Es la única receta de costillas en salsa barbacoa con Coca-Cola. «Costillas de cerdo agridulce» también lleva Coca-Cola, pero no es barbacoa. |
| q093 | solapamiento_alto, copia_literal | Es el único lomo con salsa de durazno. Pregunta un dato que está en la receta (30 min a 180 °C). |
| q095 | solapamiento_alto, copia_literal | Nombra el plato (`busqueda`) y es la única berenjena rellena de champiñones. |
| q096 | longitud, solapamiento_alto | «Arroz con lentejas y cebollas caramelizadas» se parece, pero solo esta lleva piñones. |

## Observaciones

- **Duplicado en la colección:** «Tortilla de escarola cocida» y «Tortilla de ESCAROLA Mº Carme Roca» tienen el mismo texto con diferencias mínimas de puntuación. La deduplicación exacta por (`ingredients`, `steps`) no los detecta. «Albóndigas de pescado con arroz» y «Arroz con albóndigas de carne» comparten casi todo el texto. Convendría revisar los casi-duplicados antes de indexar.
- **La ambigüedad es el problema principal (34 de 35 descartes; en 2 de ellos, además, la receta no tiene la respuesta).** Los tipos más afectados son `compra` e `ingredientes`, que tienden a describir el plato genérico. En el Hito 2 estas consultas podrían recuperarse admitiendo varios `relevant_ids` por consulta.
- Las consultas de tipo `duda` que preguntan un tiempo que la receta solo da de forma cualitativa («hasta que se abran», «hasta que estén blandas») se conservan si la consulta identifica la receta: q007, q044, q054 y q068.
