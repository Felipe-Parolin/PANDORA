"""Recuperação de informação autorizada: casos semelhantes (OS) e trechos de manuais.

O Groq não oferece embeddings; por isso a busca é lexical (BM25) sobre texto normalizado em
português. A estratégia é trocável (padrão Strategy) caso um índice vetorial seja adotado.
"""
import math
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Q

from maintenance.models import ServiceOrder

from .models import ManualChunk
from .text import tokenize, truncate


@dataclass
class Document:
    key: str
    kind: str  # "service_order" | "manual"
    title: str
    text: str
    equipment_id: int | None = None
    boost: float = 1.0
    meta: dict = field(default_factory=dict)


@dataclass
class Hit:
    document: Document
    score: float
    relevance: float = 0.0  # 0..1 relativo ao melhor resultado da busca


class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, documents: list[Document], limit: int) -> list[Hit]: ...


class BM25Retriever(Retriever):
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b

    def search(self, query, documents, limit):
        terms = set(tokenize(query))
        if not terms or not documents:
            return []
        tokenized = [Counter(tokenize(f"{doc.title} {doc.text}")) for doc in documents]
        lengths = [sum(counter.values()) for counter in tokenized]
        average = (sum(lengths) / len(lengths)) or 1
        total = len(documents)
        doc_freq = {term: sum(1 for counter in tokenized if term in counter) for term in terms}
        hits = []
        for doc, counter, length in zip(documents, tokenized, lengths):
            score = 0.0
            for term in terms:
                frequency = counter.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (total - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += idf * frequency * (self.k1 + 1) / (frequency + self.k1 * (1 - self.b + self.b * length / average))
            if score > 0:
                hits.append(Hit(doc, score * doc.boost))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        top = hits[:limit]
        if top:
            best = top[0].score
            for hit in top:
                hit.relevance = round(hit.score / best, 3)
        return top


class KnowledgeBase:
    """Monta o universo de documentos que o usuário autenticado pode consultar (RN: IA respeita ACL)."""

    ORDER_WINDOW = 600
    CHUNK_WINDOW = 3000

    def __init__(self, user):
        self.user = user

    def can_read_orders(self) -> bool:
        return self.user.has_acl("maintenance.view")

    def can_read_manuals(self) -> bool:
        return self.user.has_acl("media.view")

    def order_documents(self, equipment=None, exclude_order=None) -> list[Document]:
        if not self.can_read_orders():
            return []
        queryset = ServiceOrder.objects.select_related("equipment__category").prefetch_related("activities").order_by("-opened_at")
        if exclude_order is not None:
            queryset = queryset.exclude(pk=exclude_order.pk)
        documents = []
        for order in queryset[: self.ORDER_WINDOW]:
            same_equipment = equipment is not None and order.equipment_id == equipment.pk
            same_model = equipment is not None and order.equipment.model == equipment.model and order.equipment.brand == equipment.brand
            same_category = equipment is not None and order.equipment.category_id == equipment.category_id
            boost = 1.3 if same_equipment else 1.2 if same_model else 1.08 if same_category else 1.0
            activities = " ".join(a.description for a in order.activities.all())
            body = " ".join(filter(None, (order.symptoms, order.diagnosis, order.parts_used, order.final_tests, activities)))
            documents.append(Document(
                key=f"OS:{order.pk}", kind="service_order", title=f"{order.number} · {order.equipment.name}",
                text=f"{order.equipment.name} {order.equipment.model} {body}", equipment_id=order.equipment_id, boost=boost,
                meta={
                    "id": order.pk, "number": order.number, "status": order.status, "status_label": order.get_status_display(),
                    "type_label": order.get_maintenance_type_display(), "equipment_name": order.equipment.name,
                    "date": order.opened_at.date().isoformat(), "symptoms": order.symptoms, "diagnosis": order.diagnosis,
                    "parts_used": order.parts_used, "final_tests": order.final_tests, "released": order.released,
                    "same_equipment": same_equipment, "url": f"/manutencao?order={order.pk}",
                },
            ))
        return documents

    def manual_documents(self, equipment=None) -> list[Document]:
        if not self.can_read_manuals():
            return []
        queryset = ManualChunk.objects.select_related("media__equipment")
        if equipment is not None:
            queryset = queryset.filter(
                Q(media__equipment=equipment)
                | Q(media__equipment__brand=equipment.brand, media__equipment__model=equipment.model)
            )
        documents = []
        for chunk in queryset.distinct().order_by("media_id", "position")[: self.CHUNK_WINDOW]:
            media = chunk.media
            same_equipment = equipment is not None and media.equipment_id == equipment.pk
            documents.append(Document(
                key=f"MAN:{chunk.pk}", kind="manual", title=f"{media.name} · p. {chunk.page}", text=chunk.text,
                equipment_id=media.equipment_id, boost=1.25 if same_equipment else 1.0,
                meta={"media_id": media.pk, "manual_name": media.name, "page": chunk.page, "equipment_name": media.equipment.name if media.equipment_id else ""},
            ))
        return documents


def build_source(source_id: str, hit: Hit) -> dict:
    """Representação serializável (e rastreável) de uma fonte consultada."""
    doc = hit.document
    base = {"id": source_id, "kind": doc.kind, "title": doc.title, "relevance": hit.relevance}
    if doc.kind == "service_order":
        meta = doc.meta
        base.update({
            "excerpt": truncate(f"Sintomas: {meta['symptoms']} | Diagnóstico: {meta['diagnosis'] or '—'} | Peças: {meta['parts_used'] or '—'}", 600),
            "number": meta["number"], "status": meta["status"], "status_label": meta["status_label"],
            "type_label": meta["type_label"], "date": meta["date"], "equipment_name": meta["equipment_name"],
            "same_equipment": meta["same_equipment"], "outcome": truncate(meta["final_tests"] or meta["diagnosis"] or "", 240),
            "url": meta["url"],
        })
    else:
        base.update({
            "excerpt": truncate(doc.text, 600), "manual_name": doc.meta["manual_name"], "page": doc.meta["page"],
            "equipment_name": doc.meta["equipment_name"], "media_id": doc.meta["media_id"],
        })
    return base
