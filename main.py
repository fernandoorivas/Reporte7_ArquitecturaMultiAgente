from __future__ import annotations
import os, asyncio, argparse
from dataclasses import dataclass
from typing import Any, Dict, AsyncIterator, List
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

# PUBLISH / SUBSCRIBE
@dataclass
class Message:
    topic: str
    type: str
    payload: Dict[str, Any]
    sender: str

class MessageBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
    async def publish(self, msg: Message) -> None:
        async with self._lock:
            for q in self._subs.get(msg.topic, []):
                await q.put(msg)
    async def subscribe(self, topic: str) -> AsyncIterator[Message]:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subs.setdefault(topic, []).append(q)
        try:
            while True:
                msg: Message = await q.get()
                yield msg
        finally:
            async with self._lock:
                if topic in self._subs and q in self._subs[topic]:
                    self._subs[topic].remove(q)

# PROMPTS
RESEARCH_PROMPT = PromptTemplate(
    input_variables=["tema"],
    template=("Eres un investigador técnico. Enlista hallazgos clave y 3 referencias sobre: {tema}. "
              "Responde en español con viñetas.\n\n- Punto 1\n- Punto 2\n- Punto 3\nReferencias: [1], [2], [3]")
)
WRITER_PROMPT = PromptTemplate(
    input_variables=["tema", "research_text"],
    template=("Eres redactor técnico. Con base en la investigación, redacta un borrador en Markdown "
              "con Título, Introducción, 3–4 secciones y Conclusión. Español claro.\n\n"
              "Tema: {tema}\n\nInvestigación:\n{research_text}\n\nDevuelve solo el Markdown.")
)
EDITOR_PROMPT = PromptTemplate(
    input_variables=["draft_md"],
    template=("Eres editor. Mejora claridad, ortografía y formato Markdown del borrador. "
              "Devuelve solo el Markdown final.\n\n{draft_md}")
)

def build_llm(temperature: float) -> ChatGoogleGenerativeAI:
    model_name = os.getenv("GENAI_MODEL", "gemini-1.5-flash")
    return ChatGoogleGenerativeAI(model=model_name, temperature=temperature)

# AGENTES
class BaseAgent:
    def __init__(self, name: str, bus: MessageBus, in_topic: str):
        self.name, self.bus, self.in_topic = name, bus, in_topic
    async def run(self) -> None:
        async for msg in self.bus.subscribe(self.in_topic):
            await self.on_message(msg)
    async def on_message(self, msg: Message) -> None:
        raise NotImplementedError

class ResearchAgent(BaseAgent):
    def __init__(self, bus: MessageBus):
        super().__init__("ResearchAgent", bus, "research:request")
        temp = float(os.getenv("TEMP_RESEARCH", "0.2"))
        self.llm = build_llm(temp)
        self.chain = RESEARCH_PROMPT | self.llm | StrOutputParser()
    async def on_message(self, msg: Message) -> None:
        if msg.type != "research.request": return
        tema = msg.payload.get("tema", "")
        print(f"[Research] recibido -> tema='{tema}'")
        try:
            research_text = await asyncio.wait_for(self.chain.ainvoke({"tema": tema}), timeout=45)
            print("[Research] OK, publicando research:result")
            await self.bus.publish(Message("research:result","research.result",
                                           {"tema": tema, "research_text": research_text}, self.name))
        except Exception as e:
            print("[Research][ERROR]:", repr(e))

class WriterAgent(BaseAgent):
    def __init__(self, bus: MessageBus):
        super().__init__("WriterAgent", bus, "research:result")
        temp = float(os.getenv("TEMP_WRITER", "0.5"))
        self.llm = build_llm(temp)
        self.chain = WRITER_PROMPT | self.llm | StrOutputParser()
    async def on_message(self, msg: Message) -> None:
        if msg.type != "research.result": return
        tema = msg.payload.get("tema", "")
        research_text = msg.payload.get("research_text", "")
        print(f"[Writer] recibido research.result -> tema='{tema}'")
        try:
            draft_md = await asyncio.wait_for(
                self.chain.ainvoke({"tema": tema, "research_text": research_text}), timeout=45
            )
            print("[Writer] OK, publicando writer:draft")
            await self.bus.publish(Message("writer:draft","writer.draft",
                                           {"tema": tema, "draft_md": draft_md}, self.name))
        except Exception as e:
            print("[Writer][ERROR]:", repr(e))

class EditorAgent(BaseAgent):
    def __init__(self, bus: MessageBus):
        super().__init__("EditorAgent", bus, "writer:draft")
        temp = float(os.getenv("TEMP_EDITOR", "0.2"))
        self.llm = build_llm(temp)
        self.chain = EDITOR_PROMPT | self.llm | StrOutputParser()
    async def on_message(self, msg: Message) -> None:
        if msg.type != "writer.draft": return
        draft_md = msg.payload.get("draft_md", "")
        tema = msg.payload.get("tema", "")
        print(f"[Editor] recibido writer:draft -> tema='{tema}'")
        try:
            final_md = await asyncio.wait_for(self.chain.ainvoke({"draft_md": draft_md}), timeout=45)
            print("[Editor] OK, publicando editor:final y guardando archivo")
            await self.bus.publish(Message("editor:final","editor.final",
                                           {"tema": tema, "article_md": final_md}, self.name))
        except Exception as e:
            print("[Editor][ERROR]:", repr(e))


async def main(tema: str) -> None:
    out_dir = Path("outputs"); out_dir.mkdir(exist_ok=True)
    article_path = out_dir / "article.md"

    bus = MessageBus()
    researcher, writer, editor = ResearchAgent(bus), WriterAgent(bus), EditorAgent(bus)

    async def log_research():
        async for m in bus.subscribe("research:result"):
            print(f"[research] ← {m.sender} :: {m.type}")
    async def log_writer():
        async for m in bus.subscribe("writer:draft"):
            print(f"[writer] ← {m.sender} :: {m.type}")
    async def log_final():
        async for m in bus.subscribe("editor:final"):
            article_path.write_text(m.payload["article_md"], encoding="utf-8")
            print(f"\n Artículo final guardado en {article_path.resolve()}\n")
            break

    tasks = [
        asyncio.create_task(researcher.run()),
        asyncio.create_task(writer.run()),
        asyncio.create_task(editor.run()),
        asyncio.create_task(log_research()),
        asyncio.create_task(log_writer()),
    ]
    final_task = asyncio.create_task(log_final())

    await asyncio.sleep(0.3)

    print("[Main]")
    await bus.publish(Message("research:request","research.request",{"tema": tema},"usuario"))

    try:
        await asyncio.wait_for(final_task, timeout=180)
    except asyncio.TimeoutError:
        print("Timeout: no llegó 'editor:final' a tiempo.")
    finally:
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tema", type=str, required=True, help="Tema del artículo (obligatorio)")
    args = parser.parse_args()
    asyncio.run(main(args.tema))

