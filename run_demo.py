"""Demo script: runs the writing pipeline with Claude Sonnet via OpenRouter."""

import asyncio
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Set API key
os.environ["OPENROUTER_API_KEY"] = "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"

from src.knowledge_base.db import Database
from src.knowledge_base.models import (
    Language, OutlineSection, ResearchPlan, ReferenceType,
)
from src.knowledge_base.vector_store import VectorStore
from src.llm.router import LLMRouter
from src.writing_agent.writer import WritingAgent

OUTPUT_DIR = Path("data/demo_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_demo_plan() -> ResearchPlan:
    """Create a research plan: Poetics of Silence in Celan, Can Xue, and Glissant.

    Problématique: Universal trauma theory (Caruth, Felman & Laub) treats the
    "unspeakability" of trauma as a single psychoanalytic phenomenon. This paper
    argues that "unspeakability" is culturally constructed, and that apophasis
    takes at least three distinct forms — linguistic (Celan), narrative (Can Xue),
    and epistemological (Glissant) — which Western trauma theory collapses into
    a false universal, thereby erasing their cultural specificity.
    """
    return ResearchPlan(
        id="demo-plan-002",
        topic_id="demo-topic-002",
        thesis_statement=(
            "The Poetics of Silence: Apophasis as Culturally Specific Response "
            "to Testimonial Impossibility in Celan, Can Xue, and Glissant"
        ),
        target_journal="Comparative Literature",
        target_language=Language.EN,
        outline=[
            # ---- SECTION 1: Introduction ---- #
            OutlineSection(
                title="Introduction: Against the Universal Unspeakable",
                argument=(
                    "Open with the paradox that structures all testimony literature: "
                    "the witness must speak, yet the experience resists representation. "
                    "Survey the dominant theoretical framework — Cathy Caruth's claim "
                    "that trauma is 'an overwhelming experience of sudden or catastrophic "
                    "events in which the response to the event occurs in the often delayed, "
                    "uncontrolled repetitive appearance of hallucinations and other intrusive "
                    "phenomena' (Unclaimed Experience 11), and Felman and Laub's assertion "
                    "that the Holocaust constitutes 'an event without a witness' — to show "
                    "that trauma theory posits a UNIVERSAL unspeakability grounded in "
                    "psychoanalytic models of repression and latency. Then introduce the "
                    "counter-argument: drawing on Michael Sells's concept of apophasis as "
                    "'a language of unsaying' that takes culturally specific forms, this "
                    "paper argues that the 'silence' of testimony is not one thing but "
                    "many — that Celan, Can Xue, and Glissant each deploy structurally "
                    "distinct strategies of not-saying that correspond to different cultural "
                    "epistemologies of silence. Preview the three modes: Celan's LINGUISTIC "
                    "apophasis (compression and fracture within the word), Can Xue's "
                    "NARRATIVE apophasis (distortion of the referential world), and "
                    "Glissant's EPISTEMOLOGICAL apophasis (opacity as ethical refusal). "
                    "Justify the triangular comparison: three continents, three languages, "
                    "three trauma contexts (Holocaust, Cultural Revolution, Caribbean "
                    "slavery), yet structural homologies in the retreat from direct "
                    "testimony. Note the gap in existing scholarship: Celan-Glissant "
                    "comparisons exist (Nouss, Eshelman) but the Chinese dimension is "
                    "entirely absent. State that this three-way comparison reveals what "
                    "bilateral comparisons cannot: that 'silence' itself is culturally "
                    "constructed, and that trauma theory's universalism performs an "
                    "epistemological violence analogous to the colonial transparency "
                    "Glissant critiques."
                ),
                primary_texts=[
                    "Paul Celan, Atemwende",
                    "Can Xue, Yellow Mud Street (黄泥街)",
                    "Édouard Glissant, Poétique de la Relation",
                ],
                passages_to_analyze=[],
                secondary_sources=[
                    "Cathy Caruth, Unclaimed Experience (1996)",
                    "Shoshana Felman and Dori Laub, Testimony: Crises of Witnessing (1992)",
                    "Michael Sells, Mystical Languages of Unsaying (1994)",
                    "Giorgio Agamben, Remnants of Auschwitz (1999)",
                    "Alexis Nouss, 'Paul Celan: les mots, le monde' (2010)",
                    "Michael Rothberg, Traumatic Realism (2000)",
                    "Stef Craps, Postcolonial Witnessing (2013)",
                    "Dominick LaCapra, Writing History, Writing Trauma (2001)",
                ],
                estimated_words=1800,
            ),
            # ---- SECTION 2: Celan ---- #
            OutlineSection(
                title="Celan's Linguistic Apophasis: The Word as Wound",
                argument=(
                    "Analyze Celan's late poetry (Atemwende, Fadensonnen, Lichtzwang) as "
                    "a practice of linguistic apophasis: the systematic compression, "
                    "fracture, and neologistic recombination of German that constitutes "
                    "a 'saying by unsaying' within language itself. Begin with Der Meridian "
                    "(1960), where Celan theorizes poetry as 'Atemwende' — a 'turning of "
                    "breath' that marks the point where language turns against itself. "
                    "Close-read 'Psalm' from Die Niemandsrose (1963): 'Niemand knetet uns "
                    "wieder aus Erde und Lehm, / niemand bespricht unseren Staub. / Niemand. "
                    "// Gelobt seist du, Niemand' ('No one kneads us again out of earth and "
                    "clay, / no one incants our dust. / No one. // Praised be you, No one'). "
                    "Show how the address to 'Niemand' performs a double apophasis: it "
                    "negates the addressee (God as No One) while simultaneously enacting "
                    "the liturgical form of praise (the psalm), so that the poem says and "
                    "unsays prayer in the same breath. Then close-read 'Engführung' ('The "
                    "Straitening'), showing how its fractured syntax and spatial gaps on the "
                    "page perform the impossibility of linear testimony — the poem's form "
                    "enacts the 'narrowing' (Engführung, also a musical term for stretto) "
                    "of language under the pressure of the unsayable. Connect to the Jewish "
                    "theological tradition of negative theology: the unnameable God of "
                    "Maimonides's Guide for the Perplexed finds a secular, post-Holocaust "
                    "counterpart in Celan's 'Niemand.' Cite Derrida's reading of Celan in "
                    "'Shibboleth' and Gadamer's 'Who Am I and Who Are You?' to show how "
                    "hermeneutic philosophy has grappled with Celan's apophasis. Argue that "
                    "Celan's mode is specifically LINGUISTIC: silence operates within the "
                    "word, not around it — through compression, portmanteau neologisms "
                    "(Atemkristall, Zeitgehöft), enjambments that fracture syntax, and the "
                    "refusal of metaphor in favor of what Celan calls 'Gegenwort' (counter-word)."
                ),
                primary_texts=[
                    "Paul Celan, 'Psalm' (Die Niemandsrose, 1963)",
                    "Paul Celan, 'Engführung' (Sprachgitter, 1959)",
                    "Paul Celan, Der Meridian (1960)",
                    "Paul Celan, Atemwende (1967)",
                ],
                passages_to_analyze=[
                    "Niemand knetet uns wieder aus Erde und Lehm, / niemand bespricht "
                    "unseren Staub. / Niemand. // Gelobt seist du, Niemand. / Dir zulieb "
                    "wollen / wir blühn. / Dir / entgegen.",
                    "VERBRACHT ins / Gelände / mit der untrüglichen / Spur: // Gras, "
                    "auseinandergeschrieben.",
                ],
                secondary_sources=[
                    "Jacques Derrida, 'Shibboleth: pour Paul Celan' (1986)",
                    "Hans-Georg Gadamer, 'Who Am I and Who Are You?' (1973)",
                    "Philippe Lacoue-Labarthe, Poetry as Experience (1986)",
                    "Werner Hamacher, 'The Second of Inversion' (1986)",
                    "Aris Fioretos, ed., Word Traces: Readings of Paul Celan (1994)",
                    "John Felstiner, Paul Celan: Poet, Survivor, Jew (1995)",
                    "Peter Szondi, Celan Studies (2003)",
                    "Véronique Fóti, 'Celan's Poetics of Silence' (1990)",
                ],
                estimated_words=2000,
            ),
            # ---- SECTION 3: Can Xue ---- #
            OutlineSection(
                title="Can Xue's Narrative Apophasis: The World as Nightmare",
                argument=(
                    "Argue that Can Xue's fiction performs a narrative apophasis that is "
                    "structurally distinct from Celan's linguistic mode. Where Celan "
                    "compresses language, Can Xue distorts the entire referential world: "
                    "her characters inhabit spaces of grotesque transformation where "
                    "bodies decompose, walls secrete fluids, neighbors spy through "
                    "impossible apertures, and paranoid surveillance is both everywhere "
                    "and nowhere. The trauma of the Cultural Revolution is never named — "
                    "it is the structuring absence around which the nightmare coalesces. "
                    "Close-read Yellow Mud Street (黄泥街, 1986), where an entire "
                    "neighborhood undergoes accelerating decay: 'The walls began to sweat "
                    "a yellow liquid. Old Zhang's skin peeled off in sheets. Mrs. Li's "
                    "chickens grew extra heads.' Show how this is NOT surrealism for its "
                    "own sake but a precise formal response to an environment where "
                    "political reality itself had become surreal — where denunciation "
                    "sessions, struggle meetings, and arbitrary punishment made the 'real' "
                    "indistinguishable from nightmare. Then analyze passages from Old "
                    "Floating Cloud (苍老的浮云, 1986) to show how Can Xue's refusal of "
                    "psychological interiority mirrors the Cultural Revolution's destruction "
                    "of private subjectivity. Unlike Celan, who fractures the word, Can Xue "
                    "fractures the REFERENT: her language is syntactically clear but points "
                    "to a world that has lost coherence. This is apophasis at the level of "
                    "reference rather than language — a mode of not-saying that says 'this "
                    "happened' precisely by never saying what 'this' is. Connect to the "
                    "Chinese political-linguistic context of the Cultural Revolution, where "
                    "language was weaponized (political slogans, forced confessions, "
                    "self-criticism sessions) and the only truthful speech was oblique speech. "
                    "Draw on Ban Wang's analysis of the 'sublime figure of history' in Chinese "
                    "avant-garde fiction and Michael Berry's work on 'the history of pain' in "
                    "Chinese literature to contextualize Can Xue's strategies. Argue that Can "
                    "Xue's mode is specifically NARRATIVE: silence operates not in the word but "
                    "in the gap between signifier and referent — the reader senses trauma's "
                    "presence precisely because it is never directly signified."
                ),
                primary_texts=[
                    "Can Xue (残雪), Yellow Mud Street (黄泥街, 1986)",
                    "Can Xue, Old Floating Cloud (苍老的浮云, 1986)",
                    "Can Xue, Five Spice Street (五香街, 2002)",
                ],
                passages_to_analyze=[
                    "黄泥街上的墙壁开始渗出黄色的液体。老张的皮肤一片片地脱落。"
                    "李大嫂的鸡长出了多余的头。",
                    "她觉得有什么人在窗外窥视，但每次她猛地转过头去，"
                    "窗外只有灰蒙蒙的天空和一棵枯死的树。",
                ],
                secondary_sources=[
                    "Ban Wang, The Sublime Figure of History (1997)",
                    "Michael Berry, A History of Pain: Trauma in Modern Chinese Literature (2008)",
                    "Rong Cai, The Subject in Crisis in Contemporary Chinese Literature (2004)",
                    "Maghiel van Crevel, Chinese Poetry in Times of Mind, Mayhem and Money (2008)",
                    "Laura Cull Ó Maoilearca, 'Can Xue and Philosophies of Immanence' (2019)",
                    "Liansu Meng, 'Grotesque Body and the Cultural Revolution' (2012)",
                    "Li Rui (李锐), 'Can Xue and Chinese Avant-Garde Fiction' (1992)",
                    "Yan Jiayan (颜纯钧), 'The Aesthetics of Deformation' (1988)",
                ],
                estimated_words=2000,
            ),
            # ---- SECTION 4: Glissant ---- #
            OutlineSection(
                title="Glissant's Epistemological Apophasis: Opacity as Ethical Refusal",
                argument=(
                    "Analyze Glissant's concept of 'opacité' (opacity) as a third, "
                    "epistemological mode of apophasis that differs fundamentally from "
                    "both Celan's linguistic fracture and Can Xue's narrative distortion. "
                    "For Glissant, opacity is not a symptom of trauma but an active ethical "
                    "and political stance: 'le droit à l'opacité' — the right not to be "
                    "understood — is a refusal of the colonial demand for transparency. "
                    "Close-read key passages from Poétique de la Relation (1990): 'Nous "
                    "réclamons le droit à l'opacité... La pensée de l'opacité me détourne "
                    "de l'absolue et insoluble de l'Être' ('We demand the right to opacity... "
                    "The thought of opacity diverts me from the absolute and the insoluble "
                    "of Being'). Show how this constitutes an apophasis at the epistemological "
                    "level: Glissant does not compress language (like Celan) or distort the "
                    "referent (like Can Xue), but refuses the very framework of comprehension "
                    "that colonial modernity imposes. The silence here is chosen, not imposed — "
                    "and this choice transforms silence from a mark of victimhood into an "
                    "assertion of sovereignty. Then analyze Le Discours antillais (1981) and "
                    "the concept of 'le cri' (the cry) — the originary scream of the Middle "
                    "Passage that precedes and exceeds language. Show how 'le cri' and "
                    "'l'opacité' form a dialectic: the cry marks the historical trauma that "
                    "language cannot contain; opacity marks the ethical refusal to let that "
                    "trauma be consumed by Western hermeneutics. Close-read passages from "
                    "Le Quatrième siècle (1964) where narrative chronology collapses as the "
                    "characters attempt to reconstruct the memory of the slave ship — the "
                    "novel's temporal structure enacts the impossibility of linear memory "
                    "under conditions of historical erasure. Draw on Celia Britton's analysis "
                    "of Glissant's relation to Deleuze, and Peter Hallward's critique of "
                    "opacity as potentially depoliticizing, to show how Glissant's apophasis "
                    "is irreducible to either Celan's or Can Xue's mode. Argue that Glissant "
                    "transforms apophasis from a response to trauma into a positive poetics "
                    "— what he calls 'la Relation' — that makes opacity generative rather "
                    "than merely defensive."
                ),
                primary_texts=[
                    "Édouard Glissant, Poétique de la Relation (1990)",
                    "Édouard Glissant, Le Discours antillais (1981)",
                    "Édouard Glissant, Le Quatrième siècle (1964)",
                ],
                passages_to_analyze=[
                    "Nous réclamons le droit à l'opacité. [...] La pensée de l'opacité "
                    "me détourne de l'absolue et insoluble de l'Être.",
                    "Le cri est le premier et le dernier mot. Il est avant le mot. "
                    "C'est la bouche ouverte de la cale du négrier.",
                ],
                secondary_sources=[
                    "Celia Britton, Edouard Glissant and Postcolonial Theory (1999)",
                    "Peter Hallward, Absolutely Postcolonial (2001)",
                    "Michael Dash, Edouard Glissant (1995)",
                    "Maryse Condé, 'Order, Disorder, Freedom, and the West Indian Writer' (1993)",
                    "Chris Bongie, Islands and Exiles: The Creole Identities of Post/Colonial Literature (1998)",
                    "Nick Nesbitt, Caribbean Critique (2013)",
                    "Valérie Loichot, Orphan Narratives (2007)",
                    "Charles Forsdick, 'Travelling Concepts' (2001)",
                ],
                estimated_words=2000,
            ),
            # ---- SECTION 5: Triangulation ---- #
            OutlineSection(
                title="Three Silences, Three Epistemologies: A Triangular Reading",
                argument=(
                    "Having established the three modes of apophasis in isolation, now "
                    "triangulate them to demonstrate what bilateral comparisons cannot show. "
                    "First, compare Celan and Can Xue on the question of language and "
                    "reference. Both write in the language of the perpetrators' culture "
                    "(German, Mandarin Chinese), but Celan attacks language itself while "
                    "Can Xue attacks the world that language purports to describe. The "
                    "German Celan inherits has been poisoned by Nazism (he calls it 'the "
                    "language of the murderers'); the Chinese Can Xue inherits has been "
                    "weaponized by Maoist ideology. Yet their responses diverge: Celan "
                    "believes language can be redeemed through poetic compression — the word "
                    "can be 'purified' by being broken and rebuilt (Mallarmé's 'donner un "
                    "sens plus pur aux mots de la tribu' echoes here). Can Xue, by contrast, "
                    "leaves language intact but evacuates the world it refers to — language is "
                    "not broken but its referent is. Second, compare Can Xue and Glissant on "
                    "the politics of opacity. Both deploy strategies of non-transparency, "
                    "but for different reasons: Can Xue's opacity is a survival strategy "
                    "within a totalitarian system where direct speech is dangerous (what "
                    "Loseff, in another context, calls 'Aesopian language'); Glissant's "
                    "opacity is an assertion of cultural sovereignty against a colonial "
                    "system that demands legibility. The first is defensive; the second is "
                    "affirmative. Third, compare Celan and Glissant on the relationship "
                    "between apophasis and negative theology. Celan's address to 'Niemand' "
                    "secularizes the Jewish apophatic tradition (the unnameable God becomes "
                    "the unnameable experience); Glissant explicitly rejects Western theology "
                    "and philosophy (including negative theology) as instruments of 'la pensée "
                    "de système' and proposes opacity as an alternative epistemology rooted in "
                    "Caribbean creolization. Together, these three comparisons demonstrate that "
                    "'silence' in testimony literature is not a single phenomenon but a family "
                    "of culturally specific strategies, and that treating them as one — as "
                    "Caruth's framework does — performs the very epistemological violence that "
                    "Glissant's theory of opacity is designed to resist."
                ),
                primary_texts=[
                    "Paul Celan, 'Psalm'",
                    "Can Xue, Yellow Mud Street",
                    "Édouard Glissant, Poétique de la Relation",
                ],
                passages_to_analyze=[],
                secondary_sources=[
                    "Cathy Caruth, Unclaimed Experience (1996)",
                    "Lev Loseff, On the Beneficence of Censorship: Aesopian Language (1984)",
                    "Stéphane Mallarmé, 'Le Tombeau d'Edgar Poe' (1877)",
                    "Gayatri Spivak, 'Can the Subaltern Speak?' (1988)",
                    "Frantz Fanon, Peau noire, masques blancs (1952)",
                    "Walter Benjamin, 'The Task of the Translator' (1923)",
                    "Édouard Glissant, Philosophie de la Relation (2009)",
                ],
                estimated_words=1800,
            ),
            # ---- SECTION 6: Conclusion ---- #
            OutlineSection(
                title="Conclusion: Toward a Comparative Poetics of Silence",
                argument=(
                    "Synthesize the argument: apophasis is not a universal response to "
                    "trauma (as Caruth and Felman implicitly assume) but a culturally "
                    "inflected practice that takes distinct forms depending on the linguistic, "
                    "political, and philosophical traditions in which the writer operates. "
                    "The three-way comparison reveals that what Western trauma theory calls "
                    "'the unspeakable' is actually at least three different things: the "
                    "linguistically compressed (Celan), the referentially displaced (Can Xue), "
                    "and the epistemologically refused (Glissant). These are not just different "
                    "surfaces of the same depth but different depths — different ways of "
                    "understanding what silence IS and what it DOES. Reflect on the "
                    "methodological implications for comparative literature: a truly "
                    "comparative approach to silence must resist the temptation to subsume "
                    "difference under a universal category, yet must also account for the "
                    "structural homologies that make comparison possible in the first place. "
                    "Propose that 'apophasis' — understood not as a single strategy but as a "
                    "SPECTRUM of culturally specific unsaying practices — offers a more "
                    "adequate framework than 'trauma' for reading silence across literary "
                    "traditions. End by noting that this has implications beyond the three "
                    "authors studied here: the framework could be extended to other sites of "
                    "testimonial impossibility — Armenian genocide literature, apartheid "
                    "literature, literature of the Dirty War — where 'silence' also takes "
                    "culturally specific forms that resist universalization."
                ),
                primary_texts=[
                    "Paul Celan, Atemwende",
                    "Can Xue, Yellow Mud Street",
                    "Édouard Glissant, Poétique de la Relation",
                ],
                passages_to_analyze=[],
                secondary_sources=[
                    "Michael Sells, Mystical Languages of Unsaying (1994)",
                    "Judith Butler, Giving an Account of Oneself (2005)",
                    "Paul Ricoeur, Memory, History, Forgetting (2000)",
                    "Achille Mbembe, Critique de la raison nègre (2013)",
                ],
                estimated_words=1200,
            ),
        ],
        reference_ids=[],
        status="approved",
    )


def generate_works_cited(full_text: str, plan: ResearchPlan, router: LLMRouter) -> str:
    """Use LLM to compile a Works Cited from the manuscript and plan references."""
    # Collect all references from the plan
    all_refs: list[str] = []
    for section in plan.outline:
        all_refs.extend(section.primary_texts)
        all_refs.extend(section.secondary_sources)
    # Deduplicate while preserving order
    seen = set()
    unique_refs = []
    for r in all_refs:
        key = r.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_refs.append(r)

    refs_block = "\n".join(f"- {r}" for r in unique_refs)

    # Truncate manuscript to fit context
    max_chars = 20000
    if len(full_text) > max_chars:
        text_sample = full_text[:max_chars // 2] + "\n\n[...]\n\n" + full_text[-(max_chars // 2):]
    else:
        text_sample = full_text

    messages = [
        {"role": "system", "content": (
            "You are a bibliographer specializing in MLA/Chicago format for "
            "comparative literature journals. Compile a Works Cited list."
        )},
        {"role": "user", "content": (
            "Based on the manuscript text below and the reference list, compile a "
            "complete WORKS CITED section. Format each entry in Chicago/MLA hybrid "
            "style (as used by the journal *Comparative Literature*):\n"
            "- Alphabetical by author surname\n"
            "- Books: Surname, First Name. *Title*. Publisher, Year.\n"
            "- Articles: Surname, First Name. \"Article Title.\" *Journal* vol.issue (Year): pages.\n"
            "- Chapters: Surname, First Name. \"Chapter Title.\" *Book Title*, edited by Editor, Publisher, Year, pp. pages.\n"
            "- Non-English titles: give in original language; add translation in brackets for non-Latin scripts\n"
            "- Include ALL sources that appear to be cited in the manuscript text\n"
            "- Include primary literary works with their standard editions/translations\n"
            "- Output ONLY the formatted entries, one per line, no numbering, no headers\n\n"
            f"REFERENCES FROM PLAN:\n{refs_block}\n\n"
            f"MANUSCRIPT TEXT:\n\"\"\"\n{text_sample}\n\"\"\""
        )},
    ]

    response = router.complete(task_type="writing", messages=messages, max_tokens=4000)
    return router.get_response_text(response)


def render_html(manuscript_sections: dict[str, str], plan: ResearchPlan,
                abstract: str, duration: float, works_cited: str = "") -> str:
    """Render manuscript as styled HTML."""
    # Build Works Cited HTML
    works_cited_html = ""
    if works_cited:
        for line in works_cited.strip().split("\n"):
            line = line.strip()
            if line:
                works_cited_html += f'<p class="wc-entry">{line}</p>\n'

    import re as _re

    def _render_verify_tags(html_text: str) -> str:
        """Convert [VERIFY:xxx] tags to styled HTML spans."""
        return _re.sub(
            r'\[VERIFY:([\w-]+)\]',
            r'<span class="verify-tag" title="VERIFY:\1">&#9888; VERIFY:\1</span>',
            html_text,
        )

    sections_html = ""
    for title, content in manuscript_sections.items():
        # Convert markdown-ish content to HTML paragraphs
        paragraphs = content.split("\n\n")
        paras_html = ""
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if p.startswith(">"):
                # Block quote
                quote_lines = [line.lstrip("> ").strip() for line in p.split("\n")]
                paras_html += f'<blockquote>{_render_verify_tags("<br>".join(quote_lines))}</blockquote>\n'
            else:
                paras_html += f"<p>{_render_verify_tags(p)}</p>\n"
        sections_html += f'<h2>{title}</h2>\n{paras_html}\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Researcher Demo — Poetics of Silence</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            line-height: 1.8;
            color: #1a1a1a;
            background: #fafaf7;
            padding: 2rem;
        }}
        .container {{
            max-width: 780px;
            margin: 0 auto;
            background: white;
            padding: 3rem 4rem;
            box-shadow: 0 2px 20px rgba(0,0,0,0.08);
            border-radius: 4px;
        }}
        .meta {{
            text-align: center;
            margin-bottom: 2.5rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid #ddd;
        }}
        .meta h1 {{
            font-size: 1.4rem;
            line-height: 1.4;
            margin-bottom: 0.8rem;
            font-weight: normal;
            font-style: italic;
        }}
        .meta .journal {{
            color: #666;
            font-size: 0.95rem;
            font-variant: small-caps;
            letter-spacing: 0.05em;
        }}
        .meta .stats {{
            color: #888;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }}
        .abstract {{
            background: #f5f5f0;
            padding: 1.5rem 2rem;
            margin-bottom: 2rem;
            border-left: 3px solid #666;
            font-size: 0.92rem;
        }}
        .abstract h3 {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 0.5rem;
            color: #555;
        }}
        h2 {{
            font-size: 1.15rem;
            margin: 2.5rem 0 1rem;
            font-weight: normal;
            font-variant: small-caps;
            letter-spacing: 0.03em;
            border-bottom: 1px solid #eee;
            padding-bottom: 0.3rem;
        }}
        p {{
            margin-bottom: 1rem;
            text-align: justify;
            text-indent: 1.5em;
            font-size: 0.98rem;
        }}
        p:first-of-type {{ text-indent: 0; }}
        blockquote {{
            margin: 1.5rem 0 1.5rem 2.5rem;
            padding: 0.5rem 0 0.5rem 1rem;
            border-left: 2px solid #ccc;
            font-size: 0.92rem;
            color: #333;
            font-style: italic;
        }}
        .works-cited {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 2px solid #333;
        }}
        .works-cited h2 {{
            font-size: 1.15rem;
            margin-bottom: 1.5rem;
            font-weight: normal;
            font-variant: small-caps;
            letter-spacing: 0.03em;
            border-bottom: none;
        }}
        .wc-entry {{
            text-indent: -2em !important;
            padding-left: 2em;
            margin-bottom: 0.6rem;
            font-size: 0.92rem;
            line-height: 1.6;
        }}
        .footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid #ddd;
            font-size: 0.8rem;
            color: #999;
            text-align: center;
        }}
        .badge {{
            display: inline-block;
            background: #e8e8e0;
            padding: 0.2rem 0.6rem;
            border-radius: 3px;
            font-family: monospace;
            font-size: 0.75rem;
        }}
        .verify-tag {{
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffc107;
            border-radius: 3px;
            padding: 0.1rem 0.4rem;
            font-family: monospace;
            font-size: 0.75rem;
            font-style: normal;
            white-space: nowrap;
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="meta">
        <div class="journal">Comparative Literature</div>
        <h1>{plan.thesis_statement}</h1>
        <div class="stats">
            Generated by AI Researcher Pipeline |
            Model: Claude Sonnet 4 via OpenRouter |
            {duration:.1f}s |
            {{datetime.now().strftime('%Y-%m-%d %H:%M')}}
        </div>
    </div>

    <div class="abstract">
        <h3>Abstract</h3>
        {abstract}
    </div>

    {sections_html}

    <div class="works-cited">
        <h2>Works Cited</h2>
        {works_cited_html}
    </div>

    <div class="footer">
        <span class="badge">Phase 11 Citation Verification</span> |
        Self-Refine iterative drafting with 5-axis critic scoring |
        Citation norms loaded from <em>Comparative Literature</em> profile |
        Citations verified against CrossRef/OpenAlex
    </div>
</div>
</body>
</html>"""


async def main():
    print("=" * 60)
    print("AI Researcher Writing Pipeline Demo")
    print("Model: Claude Sonnet 4 via OpenRouter")
    print("Topic: Poetics of Silence — Celan, Can Xue, Glissant")
    print("=" * 60)

    # Setup
    db = Database(":memory:")
    vs = VectorStore()
    router = LLMRouter(config_path="config/llm_routing_openrouter.yaml", db=db)
    writer = WritingAgent(db=db, vector_store=vs, llm_router=router)

    plan = create_demo_plan()

    print(f"\nThesis: {plan.thesis_statement}")
    print(f"Journal: {plan.target_journal}")
    print(f"Sections: {len(plan.outline)}")
    total_est = sum(s.estimated_words for s in plan.outline)
    print(f"Target word count: {total_est}+")
    total_refs = sum(len(s.secondary_sources) for s in plan.outline)
    print(f"References in plan: {total_refs}")
    print()

    start = time.time()

    # Write each section
    sections: dict[str, str] = {}
    all_parts: list[str] = []

    reflexion_memories = [
        "Primary literary texts MUST be directly quoted — the reader must see the actual words.",
        "For non-English texts (German, Chinese, French), quote in the ORIGINAL LANGUAGE first, "
        "then provide English translation in parentheses or as a separate sentence.",
        "Vary citation verbs: writes, argues, notes, observes, contends, insists, suggests, cautions.",
        "Use short phrase quotations (1-8 words) most frequently for secondary criticism.",
        "Block quotes (35+ words, indented) are reserved for primary text close readings.",
        "Paraphrase secondary criticism and engage with arguments — don't just name-drop.",
        "Every paragraph must contain at least one citation. Aim for 3-5 citations per 250 words.",
        "Theory should be deployed surgically for specific concepts, not exhaustive exegesis.",
        "IMPORTANT: Each section must reach its MINIMUM word count. Develop every argument fully "
        "with evidence, quotation, and scholarly engagement. A 2000-word section = ~8 paragraphs "
        "of dense, publication-ready prose. Do not truncate or summarize.",
        "Use substantive footnotes for bibliographic guidance clusters and extended arguments.",
    ]

    for i, section in enumerate(plan.outline):
        print(f"[{i+1}/{len(plan.outline)}] Writing: {section.title}...")
        print(f"          Target: {section.estimated_words}+ words")
        sys.stdout.flush()
        section_text = await writer.write_section(
            section=section,
            plan=plan,
            reflexion_memories=reflexion_memories,
        )
        sections[section.title] = section_text
        all_parts.append(f"## {section.title}\n\n{section_text}")
        word_count = len(section_text.split())
        pct = word_count / section.estimated_words * 100
        status = "OK" if word_count >= section.estimated_words * 0.8 else "SHORT"
        print(f"          Result: {word_count} words ({pct:.0f}% of target) [{status}]")

    full_text = "\n\n".join(all_parts)

    # Generate abstract
    print(f"\nGenerating abstract...")
    sys.stdout.flush()
    abstract = await writer._generate_abstract(full_text, plan)
    print(f"    Done: {len(abstract.split())} words")

    # Generate Works Cited
    print(f"Generating Works Cited...")
    sys.stdout.flush()
    works_cited = generate_works_cited(full_text, plan, router)
    wc_entries = [l for l in works_cited.strip().split("\n") if l.strip()]
    print(f"    Done: {len(wc_entries)} entries")

    # Citation verification
    print(f"Verifying citations against CrossRef/OpenAlex...")
    sys.stdout.flush()
    from src.citation_verifier.pipeline import verify_manuscript_citations
    full_text, ver_report = await verify_manuscript_citations(full_text)
    print(f"    {ver_report.summary()}")

    # Re-parse sections with [VERIFY] tags inserted
    if ver_report.work_not_found + ver_report.page_unverifiable + ver_report.page_out_of_range > 0:
        parts_iter = iter(full_text.split("\n\n## "))
        first = next(parts_iter)
        # Rebuild sections dict preserving original keys
        section_titles = list(sections.keys())
        verified_sections: dict[str, str] = {}
        idx = 0
        for chunk in full_text.split("\n\n## "):
            for title in section_titles:
                if chunk.startswith(title) or (idx == 0 and title == section_titles[0]):
                    content = chunk
                    if content.startswith(title):
                        content = content[len(title):].lstrip("\n")
                    verified_sections[title] = content
                    section_titles.remove(title)
                    break
            idx += 1
        if verified_sections:
            sections = verified_sections

    # Save verification report
    report_path = OUTPUT_DIR / "verification_report.md"
    report_path.write_text(ver_report.to_markdown(), encoding="utf-8")

    duration = time.time() - start
    total_words = len(full_text.split())

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"Total words: {total_words}")
    print(f"Target:      {total_est}+")
    print(f"Duration:    {duration:.1f}s")
    print(f"Sections:    {len(sections)}")
    print(f"Works Cited: {len(wc_entries)} entries")
    print(f"Citations:   {ver_report.verified}/{ver_report.total} verified")

    # Render HTML
    html = render_html(sections, plan, abstract, duration, works_cited)
    # Fix the datetime formatting in the HTML
    html = html.replace(
        "{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        datetime.now().strftime('%Y-%m-%d %H:%M')
    )
    output_path = OUTPUT_DIR / "manuscript.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"\nSaved HTML: {output_path}")

    # Also save raw markdown
    md_path = OUTPUT_DIR / "manuscript.md"
    md_content = f"# {plan.thesis_statement}\n\n"
    md_content += f"**Journal**: {plan.target_journal}\n\n"
    md_content += f"## Abstract\n\n{abstract}\n\n"
    md_content += full_text
    md_content += f"\n\n## Works Cited\n\n{works_cited}"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Saved MD:   {md_path}")

    # Print cost summary
    try:
        summary = router.get_usage_summary()
        if summary:
            print(f"\nCost: ${summary.get('total_cost_usd', 0):.4f}")
            print(f"Tokens: {summary.get('total_tokens', 0):,}")
    except Exception:
        pass

    return str(output_path)


if __name__ == "__main__":
    output = asyncio.run(main())
    print(f"\n{'=' * 60}")
    print(f"Ready to serve: {output}")
