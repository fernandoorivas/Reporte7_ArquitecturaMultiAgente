# Reporte7_ArquitecturaMultiAgente

Nombre: Fernando Agustín Hernández Rivas <br>
Matrícula: 195468 <br>
Materia: Agentes Inteligentes <br>
Otoño 2025 <br>

## Sistema multiagente horizontal (Research → Writer → Editor)

### Introducción
Sistema multiagente en colaboración entre pares que automatiza la generación de un artículo de blog en tres etapas: investigación, redacción y edición. Implementado en Python con LangChain y Gemini.

#### Objetivo
Dividir un flujo complejo en roles especializados que colaboren para producir un resultado de mayor calidad.

#### Roles
- ResearchAgent: investiga el tema y produce hallazgos en viñetas.
- WriterAgent: transforma la investigación en un borrador Markdown.
- EditorAgent: mejora claridad, ortografía y formato; entrega el artículo final.

### Desarrollo de la solución

#### Tecnologías 
- Python 3.10+
- langchain, langchain-google-genai, google-generativeai, python-dotenv

#### Arquitectura (Clases principales)
- Message (dataclass)
  - Qué es: contenedor de mensajes.
  - Campos: topic (tópico), type (tipo/evento), payload (dict de datos), sender (quién envía).
  - Para qué sirve: estandariza la comunicación entre agentes. <br>
- MessageBus
  - Qué es: bus pub/sub en memoria (colas por tópico).
  - Métodos clave:
    - publish(msg): envía Message a todos los suscriptores del topic.
    - subscribe(topic): async generator que entrega mensajes publicados en ese topic.
    - Para qué sirve: desacoplar agentes (nadie llama directo a otro). <br>
- BaseAgent
  - Qué es: clase base de agentes.
  - Campos: name, bus, in_topic.
  - Métodos:
    - run(): loop asíncrono consumiendo in_topic.
    - on_message(msg): abstracto, cada agente implementa su lógica.
    - Para qué sirve: patrón común para crear más agentes fácilmente.
- ResearchAgent
  - Suscribe: research:request (espera {tema}).
  - Publica: research:result (entrega {tema, research_text}).
  - Qué hace: llama al LLM con prompt de investigación (viñetas + referencias breves).
- WriterAgent
  - Suscribe: research:result (usa {tema, research_text}).
  - Publica: writer:draft (entrega {tema, draft_md}).
  - Qué hace: llama al LLM con prompt de redacción para producir Markdown (título, intro, secciones, conclusión).
- EditorAgent
  - Suscribe: writer:draft (usa {draft_md, tema}).
  - Publica: editor:final (entrega {tema, article_md}).
  - Qué hace: llama al LLM con prompt de edición (mejora claridad/ortografía/estilo en Markdown).
- Prompts por rol
  - RESEARCH_PROMPT: guía de hallazgos y referencias.
  - WRITER_PROMPT: guía de estructura Markdown.
  - EDITOR_PROMPT: guía de corrección y formato final.

### Pruebas
La evidencia del funcionamiento se encuentra en **`outputs/article.md`**, donde se guarda el artículo final generado.

### Conclusión
La solución demuestra que una arquitectura multiagente horizontal con pub/sub permite desacoplar roles (Research, Writer y Editor), escalar y extender fácilmente el sistema, y mantener un flujo robusto. El uso de prompts especializados por rol mejora la calidad del texto y evita dependencias deprecadas.

