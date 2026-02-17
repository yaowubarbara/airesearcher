#!/usr/bin/env python3
"""Seed the database with 8 curated research directions and 80 topics.

Directions are derived from 133 core comp-lit journal papers.
Topics use NOVEL authors/works — never the same as corpus papers.
No Holocaust-specific topics.

Usage:
    python scripts/seed_directions.py [--dry-run]
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge_base.db import Database
from src.knowledge_base.models import ProblematiqueDirection, TopicProposal

# ---------------------------------------------------------------------------
# Paper ID mappings (from /tmp/core_papers.json — the 133 core comp-lit papers)
# ---------------------------------------------------------------------------

# Direction 1: Translation, Multilingualism, and Opacity
D1_PAPER_IDS = [
    "b4823fe3-80f7-483e-8f1b-d27e4b4c2864",  # Blomgren (Ferré, cannibalized language)
    "93146f35-f31d-4ffd-aa40-93fef0dabbb3",  # Bermann (Glissant, translation as relation)
    "3595d8f5-68ac-4866-85ef-c6857ae8cb42",  # Ramazani (mourning in translation)
    "ec393dcf-8195-4610-a354-8601b9797934",  # Saxena (multilingualism, infrastructures of loss)
    "22efb074-5f32-4ad6-aa9b-5d4ef0e26d0d",  # Bretan (Conrad, language politics)
    "d8ad1f44-9933-4a7d-a66b-ca25ea886fb1",  # Garcia (Celtic minstrelsy in Persian)
    "5d1df7fb-b40d-48ab-becb-dd5cac8f6658",  # Guest (herméneutique, decolonizing signs)
    "a2b60922-7066-464d-99c3-20274ada8683",  # Xu (posthuman multilingualism Canton)
    "dfe65c13-5039-4cf1-9831-945ce476d629",  # Raschi (Newton translations 18C France)
]

# Direction 2: Trauma, Memory, and Poetic Form
D2_PAPER_IDS = [
    "ab9f3c4d-b467-4350-bb5f-dca23d8038bf",  # Feldman (Celan, Pagis)
    "6f432a75-2181-46bc-8320-c03e2d051270",  # Hirsch (postmemory)
    "cd5d2c59-e7cb-4cd4-879d-3f31eee1fdb9",  # Haraldsen (collaborative remembering, Salvayre)
    "736ed6e8-c905-4aad-afff-bba0179263ea",  # Merritt (Ayim, Diagne haunting poetics)
    "f3319bd2-39cf-4611-942b-146283e8d896",  # Proulx (Lafontaine, post-traumatic)
    "6faff652-6e9a-4da1-befa-069eaead0aac",  # Cooper (El Akkad, queer cli-fi trauma)
    "f556685b-7fcb-4830-b8b0-9f702bbc6cf9",  # Yacobi (fiction and silence, Pagis)
    "53699930-4106-49fe-a83b-fd36b4f3095f",  # Chai (White Dust archival urn)
]

# Direction 3: Romanticism's Cross-Cultural Migrations
D3_PAPER_IDS = [
    "e37aad1f-16b5-4043-8078-53c9255b8fb3",  # Solanki (Ramayana, German Romanticism)
    "637e2b2d-011b-4ac0-8721-78b07a9b38f8",  # Mendoza/Solanki (Sensing Migrant Romanticism)
    "bee9e331-63a6-40db-b926-021309f873a9",  # Chander (Migrant Sense and Sensibility)
    "a753e720-7243-4e6c-a41c-cf526c4d3ea1",  # Narayan (Black Hole, empire, Romanticism)
    "3ea74e74-cf55-4e93-8115-2dda45ba70a1",  # Jao (Garnet, Black Romanticism)
    "e664b33e-8350-40e9-abaa-319adf0c3e51",  # Rodriguez (Isaacs, Colombia, Romantic hero)
    "a109a4fd-dd8f-4dda-b2b0-7c09a3e149a0",  # Gilbert-Santamaria (Don Quixote, Romanticism)
    "8aaf465f-cce1-41d7-af69-956714c5fa0c",  # Klinger (Gulf Stream novel)
    "024d36e8-426c-4665-94f8-13e684a3d38f",  # Castelli (Magic Realism, Chinese postmodernity)
]

# Direction 4: Canon Formation, Institutional Power, and World Literature
D4_PAPER_IDS = [
    "3ca5f460-0890-4f9d-992a-b42d6e2be621",  # Hentea (PEN, global republic of letters)
    "bfe2286b-99ee-4dff-86ec-8cef63d1cedc",  # Anders (Japanese empire, League of Nations)
    "b1545f9a-e2ba-4ab3-b979-fcf525bc3624",  # Xiang (Hikmet, solidarity poetry)
    "787f8731-b91c-4d58-8086-015470bc2670",  # Musila (fugitive forms)
    "a44ac75b-f300-42a7-bb4e-91989090a2db",  # Barnard (Otelo Burning)
    "dcd996b8-ee4b-4009-aceb-a74f95c9f2ac",  # Dewulf (Carolingian in Portuguese empire)
    "bb097eb7-3727-45d6-962b-2a210f773ab6",  # Vatulescu (archival turns intro)
    "2dc140f4-a8e6-47f5-b3c1-0696f11cdd2a",  # Stoler (archival light, praxis)
    "d32c3f68-5622-4c82-8509-03f1985c7734",  # Gvili (sympathetic reader, transnational)
    "88c0011a-c4cf-48b2-ab6d-409a224d1130",  # Fyfe/Jolly (African forms, simultaneous reading)
]

# Direction 5: Formalism and Methodology
D5_PAPER_IDS = [
    "d085f638-ddaa-426f-95b7-e501901b112b",  # Mrugalski (postimperial formalism)
    "c6c35097-eb11-42bc-a598-cd5d1be234bb",  # Oushakine (Tynianov)
    "0c1deed4-80d8-49a2-b97b-d907de81268f",  # Lipovetsky (Shklovsky parody)
    "16bab0aa-8f1c-41c3-b444-8fbfdba013ce",  # Pilshchikov (quantitative formalism)
    "6f4bde8a-ac6b-41a6-b9ae-81edf2e9f820",  # Kalinin (Shklovsky, evolution)
    "1206cf36-c1b6-48c5-86a1-1cdca4905569",  # Ioffe (Malevich, Khlebnikov)
    "75cb6183-a5db-48c9-b540-caeed6e5f289",  # Tripiccione (Shklovsky in Italy)
    "6afd6bd1-c73d-44c9-8daf-ece4655c649f",  # Ustinov (Aizenshtok, OPOIAZ)
    "ed001305-6017-42b0-8144-762f386b29de",  # Richardson (circular fiction)
    "e0af070a-03a7-4de0-b230-a3d275292e91",  # Renard (circumstantial view)
    "267c5676-3047-4b58-935a-d1418c203e7f",  # Lang (fictionality, rhetoric)
    "3d1be87f-f986-406b-bbf7-6b9b4b323242",  # Punday (fictionality, infrastructure)
    "fb3b1bb8-951f-4dd0-adbb-af33e75cab15",  # Kurmann (Sartrean reader)
    "f3754a91-f8b7-4b16-95ca-9d0086ed95ba",  # Willemsen (narrative play, epistemic emotions)
    "4310ddd3-8bf6-41ef-a36d-bcec185f3da3",  # Quintane (montage, malaise)
    "98bf21b2-0cad-460c-aeae-018a9ee46c7f",  # Wourm (Cadiot, Maestri, Chaton montage)
    "13d09a20-66a4-497e-94fd-38bb040e73ea",  # Huppe (RLG, cut-up militants)
]

# Direction 6: Postcolonial / Decolonial Critique
D6_PAPER_IDS = [
    "8672089a-a96e-4087-a53c-6b7ac0084719",  # Gifford (Orientalism, Durrell)
    "6ea76cca-b3b2-44e4-b12c-2c1f43f344bd",  # Khanna (intro Said forum)
    "8a6f805e-6ed3-4b69-b1da-98a9b0ceb77b",  # Reilly (Analysis in Exile)
    "91da510e-8a5f-462d-8a2f-34eb2d0bf4c4",  # Edelman (Said and the Non-Freudian)
    "97ddda8c-d5f3-453e-bdc4-bcc62c809b03",  # Mukherjee (Said and Non-European)
    "4f9d26e4-dc6d-4e00-8758-258e941550e5",  # Al-Kassim (Freud, Non-European)
    "7a628ece-efa5-41a6-8a0c-7fed9510ee36",  # Negrete (Wound as Opening)
    "07d47615-6867-4a0a-9018-5582065bba5e",  # Khanna/Spivak conversation
    "d1ace37c-0e26-48c9-8126-33b377fdaa0c",  # Kelly (Balagtas, coloniality)
    "4e68398a-30cb-4b33-a0cc-0322d99840ad",  # Lee (Anacaona, tragedy of origins)
    "9f858cf9-1727-4469-b133-719c90a443ef",  # Lee (Oroonoko, honor and slavery)
    "df7db46a-e34c-4fa9-a5d5-d7f31950a60e",  # Bhagat (Cold War extraction, Indian/Russian SF)
    "54481064-9a65-4546-8912-25da69fee6af",  # Norgaard (Bandung/Havana, poetry)
    "1786ad66-4ff0-4086-b267-62707a79ff9c",  # Kulez (South-South, Erdoğan)
    "1de132b4-35c7-4278-8444-1372f6558f29",  # Nyawalo (Smith, Stone Face, racial politics)
]

# Direction 7: Gender, Sexuality, and Embodiment
D7_PAPER_IDS = [
    "df175dcc-d7a2-4e6a-b900-92a0f867f2bb",  # Davis-Secord (trans saints OE)
    "e8638dda-23c2-48ca-bab3-99c76a7a339a",  # DeWitt (Thoreau, gender, ecology)
    "3ec68679-3389-4148-85f2-0ad905247e1b",  # Bartlett/Crocker (Dorigen, Chaucer)
    "4f1608cc-4ad2-4075-844e-12d08f4373f5",  # Bélanger/Brassard (Flaubert, genre)
    "28e9b0ff-ccba-4dcb-9947-0b1d7d32bdab",  # Knutsen (Rachilde, Rodenbach)
    "8087b81d-6486-4636-a750-8dcf140b64c6",  # Ménard (Sand, sexual disorders)
    "da11d7f3-8906-47a0-acc9-eb1c11b795e5",  # Heck (Zola, lesbianism)
    "889a19b3-fdc8-486a-b501-5f3ace75bf27",  # Islert (Vaudère, Demi-sexes)
    "d898e4b0-0791-44be-8223-7f80187a6eaa",  # Thiriot (Choiseul-Meuse)
    "482fc57b-1da1-45ba-b5c0-57188212b625",  # Grommerch (Eekhoud)
    "332ef454-3e3d-4d4c-ae5e-ddb2f41d7d63",  # Barda (montage, gender, poetry)
    "c21c2a06-9b5b-4a31-8ef7-442d5ea03f84",  # Bodier (Westworld, queer)
    "ac41f011-fbff-48df-b25c-83dba8c435b0",  # Rioton (queer mutation)
    "d4ed6b28-6dfe-43dc-8b5e-e95180dfa798",  # Clère (ovariectomy novels)
    "f5d27cd9-4fa5-435c-8d69-aeaedfe4767f",  # Daouda (decadent incest)
    "f9d703ca-3b13-4f58-8672-c07a64b78ee9",  # Khanna (Sex and Death, scales)
]

# Direction 8: Far-Right Narratives and Political Aesthetics
D8_PAPER_IDS = [
    "2fa7c216-8083-4e5e-bcee-8089f7c24e4f",  # Seauve (intro metapolitics)
    "a1d13080-aaa5-43ac-876a-648465c950a0",  # Schäfer (Don't Look Up, satire)
    "22a8bfeb-f713-4e14-81e9-bbf6f3666428",  # Wink (Kucinski, Brazil)
    "d8627452-6d87-4cf2-8bc9-2d603ec5c423",  # Bartolini (Melandri, Italy)
    "8192dbeb-eecc-40f4-9d24-4b8dd84da829",  # Eser (Rojas, Argentina)
    "e764f951-6c87-4f1b-8397-2c59e19ef44d",  # Pettitt (British far right fiction)
    "aea895bb-d2f7-4160-836c-837d1bddfacb",  # Hoffmann (German New Right)
]


# ---------------------------------------------------------------------------
# 8 Directions
# ---------------------------------------------------------------------------

DIRECTIONS = [
    ProblematiqueDirection(
        title="Translation, Multilingualism, and Opacity",
        description=(
            "How do literary texts negotiate the tension between translatability and "
            "opacity across languages and cultural systems? This direction examines "
            "self-translation, multilingual layering, and the ethics of untranslatability "
            "as both literary practice and theoretical problem. Its blind spot is the "
            "material infrastructure (publishing, editing, market forces) that shapes "
            "which multilingual strategies reach audiences."
        ),
        dominant_tensions=[
            "translatability ↔ constitutive opacity",
            "linguistic fidelity ↔ creative appropriation",
        ],
        dominant_mediators=[
            "self-translation as identity performance",
            "multilingual textual layering as decolonial praxis",
        ],
        dominant_scale="mediational",
        dominant_gap="incommensurability_blindspot",
        paper_ids=D1_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Trauma, Memory, and Poetic Form",
        description=(
            "How do literary forms register, transmit, and transform collective trauma "
            "across generations and cultural traditions? This direction studies the formal "
            "strategies — temporal collapse, fragmentary poetics, negative attestation — "
            "through which literature mediates between individual wound and collective "
            "memory. Its blind spot is the risk of aestheticizing suffering by reducing "
            "diverse historical traumas to a single theoretical framework."
        ),
        dominant_tensions=[
            "testimony ↔ silence",
            "individual wound ↔ collective memory transmission",
        ],
        dominant_mediators=[
            "negative poetics as ethical witness",
            "temporal folding across generational memory",
        ],
        dominant_scale="perceptual",
        dominant_gap="temporal_flattening",
        paper_ids=D2_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Romanticism's Cross-Cultural Migrations",
        description=(
            "How do Romantic aesthetic categories — the sublime, sensibility, national "
            "folk genius — migrate across cultural and linguistic boundaries, transforming "
            "both the receiving tradition and the concept itself? This direction traces "
            "Romanticism as a migrant phenomenon, studying how non-European literary "
            "traditions creatively appropriate, contest, or redirect Romantic ideas. "
            "Its blind spot is the power asymmetry in who gets to define what counts "
            "as 'Romantic' across unequal literary systems."
        ),
        dominant_tensions=[
            "European aesthetic origin ↔ non-European creative appropriation",
            "Romantic universalism ↔ colonial power asymmetry",
        ],
        dominant_mediators=[
            "sensory regime as cross-cultural transfer medium",
            "bardic nationalism across literary traditions",
        ],
        dominant_scale="mediational",
        dominant_gap="scale_mismatch",
        paper_ids=D3_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Canon Formation, Institutional Power, and World Literature",
        description=(
            "How do institutions — publishers, prize committees, international "
            "organizations, anthologies, archives — shape what circulates as 'world "
            "literature' and who is included or excluded? This direction examines the "
            "material and bureaucratic mechanisms behind canonization, asking how "
            "institutional gatekeeping interacts with literary form. Its blind spot "
            "is the tendency to critique institutions abstractly without close reading "
            "the literary texts that move through them."
        ),
        dominant_tensions=[
            "cosmopolitan universalism ↔ nationalist literary politics",
            "institutional archive ↔ fugitive cultural memory",
        ],
        dominant_mediators=[
            "international literary institutions as canon gatekeepers",
            "archival practice as power technology",
        ],
        dominant_scale="institutional",
        dominant_gap="mediational_gap",
        paper_ids=D4_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Formalism, Narratology, and Methodology",
        description=(
            "What happens when formalist and narratological methods — developed largely "
            "within European literary traditions — are applied to non-Western texts, "
            "digital corpora, or contemporary media? This direction interrogates the "
            "implicit assumptions of literary-critical methodology, from Russian "
            "Formalism to digital humanities. Its blind spot is the reluctance to "
            "test whether methods developed for one tradition are genuinely "
            "portable across literary systems."
        ),
        dominant_tensions=[
            "formal autonomy ↔ socio-historical determination",
            "qualitative close reading ↔ computational pattern detection",
        ],
        dominant_mediators=[
            "defamiliarization as transferable critical method",
            "literary evolution as dialectic of convention and innovation",
        ],
        dominant_scale="methodological",
        dominant_gap="method_naturalization",
        paper_ids=D5_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Postcolonial and Decolonial Critique",
        description=(
            "How do literary texts from formerly colonized societies challenge, rework, "
            "or refuse metropolitan frameworks of knowledge? This direction examines "
            "the literary strategies — counter-archive, exilic discourse, South-South "
            "comparison — through which postcolonial writing contests epistemological "
            "hegemony. Its blind spot is the tendency to read all non-Western literature "
            "through the postcolonial lens, collapsing distinct historical situations "
            "into a single oppositional framework."
        ),
        dominant_tensions=[
            "metropolitan knowledge production ↔ subaltern epistemology",
            "universalist humanism ↔ irreducible cultural difference",
        ],
        dominant_mediators=[
            "exilic discourse as critical methodology",
            "counter-archive as decolonial literary practice",
        ],
        dominant_scale="institutional",
        dominant_gap="incommensurability_blindspot",
        paper_ids=D6_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Gender, Sexuality, and Embodiment",
        description=(
            "How do literary texts construct, subvert, or reimagine gendered and sexual "
            "subjectivities through formal and rhetorical means? This direction studies "
            "the poetics of the unsaid, queer temporalities, and embodied language as "
            "sites where normative gender scripts are simultaneously inscribed and "
            "undone. Its blind spot is the risk of projecting contemporary gender "
            "categories onto historical texts without attending to period-specific "
            "sexual epistemologies."
        ),
        dominant_tensions=[
            "normative gender scripts ↔ textual subversion",
            "embodied desire ↔ discursive silence or constraint",
        ],
        dominant_mediators=[
            "poetics of the unsaid as queer resistance",
            "formal innovation as gender transgression",
        ],
        dominant_scale="textual",
        dominant_gap="mediational_gap",
        paper_ids=D7_PAPER_IDS,
    ),
    ProblematiqueDirection(
        title="Far-Right Narratives and Political Aesthetics",
        description=(
            "How do literary and narrative forms serve, resist, or anatomize far-right "
            "and authoritarian political projects? This direction examines both the "
            "cultural production of the New Right (metapolitics, nostalgia fiction, "
            "myth-making) and literary responses to authoritarianism (satire, dystopia, "
            "counter-narrative). Its blind spot is the tendency to treat far-right "
            "cultural production as merely propagandistic rather than analyzing its "
            "genuine aesthetic strategies."
        ),
        dominant_tensions=[
            "democratic cultural pluralism ↔ authoritarian aesthetic capture",
            "satirical critique ↔ meta-political narrative strategy",
        ],
        dominant_mediators=[
            "metapolitical fiction as ideological infrastructure",
            "satirical counter-narrative as democratic resistance",
        ],
        dominant_scale="institutional",
        dominant_gap="method_naturalization",
        paper_ids=D8_PAPER_IDS,
    ),
]


# ---------------------------------------------------------------------------
# 80 Topics (10 per direction)
#
# RULE: No author or work may duplicate one studied in the 133 core papers.
# RULE: No Holocaust-specific topics.
# RULE: Every topic must be comparative (2+ traditions/languages).
# ---------------------------------------------------------------------------

TOPICS_BY_DIRECTION = {
    0: [  # Translation, Multilingualism, and Opacity
        TopicProposal(
            title="Translingual Opacity in Yoko Tawada's German-Japanese Border Crossings",
            research_question=(
                "How does Yoko Tawada's dual-language practice in Überseeerinnerungen "
                "and Schwager in Bordeaux construct a poetics of opacity that differs from "
                "Glissantian créolité?"
            ),
            gap_description=(
                "Studies of translingual writing rarely compare East Asian and Caribbean "
                "theories of opacity. Tawada's German-Japanese work offers a case where "
                "opacity arises not from colonial history but from the incommensurability "
                "of logographic and alphabetic sign systems."
            ),
        ),
        TopicProposal(
            title="Self-Translation as Self-Cannibalization in Beckett's French-English Doubles",
            research_question=(
                "How does Samuel Beckett's systematic auto-translation between French "
                "and English dismantle the concept of an 'original,' and what does this "
                "reveal about the ethics of translingual authorship?"
            ),
            gap_description=(
                "Although Beckett's bilingualism is well documented, few studies apply "
                "the cannibalist translation framework developed for Latin American "
                "writing to his practice. This topic tests whether anthropophagy as "
                "literary theory travels across the North-South divide."
            ),
        ),
        TopicProposal(
            title="Multilingual Interference in Giannina Braschi's Yo-Yo Boing! and Khairani Barokka's Lyrics",
            research_question=(
                "How do Braschi's Spanish-English code-switching and Barokka's "
                "Indonesian-English multilingual poetics construct linguistic sovereignty "
                "within dominant Anglophone literary markets?"
            ),
            gap_description=(
                "Comparative analysis of US Latina and Southeast Asian translingual "
                "poetry is virtually absent. Both operate within English-dominant "
                "publishing yet deploy bilingualism for radically different political "
                "and aesthetic ends."
            ),
        ),
        TopicProposal(
            title="Translating Revolution: Aimé Césaire's Cahier in English and Spanish Afterlives",
            research_question=(
                "How do competing English and Spanish translations of Césaire's Cahier "
                "d'un retour au pays natal reshape its decolonial poetics for distinct "
                "Anglophone and Hispanophone reception communities?"
            ),
            gap_description=(
                "Translation studies of Césaire tend to focus on the French-English axis. "
                "No sustained comparison exists with the Spanish translations that "
                "circulated in Latin American revolutionary movements of the 1960s-70s, "
                "where the poem's political valence shifted substantially."
            ),
        ),
        TopicProposal(
            title="Maghrebi Translation Theory: Kilito's La Langue d'Adam and Khatibi's Amour bilingue",
            research_question=(
                "How do Abdelfattah Kilito and Abdelkébir Khatibi develop competing "
                "literary-philosophical models of Arabic-French bilingualism, and what "
                "do these reveal about the impossibility of linguistic ownership?"
            ),
            gap_description=(
                "Francophone postcolonial studies rarely compare Kilito and Khatibi as "
                "parallel theorists of bilingualism. Both write from Morocco, but their "
                "models of the Arabic-French linguistic relation diverge fundamentally "
                "in ways that illuminate distinct mediational strategies."
            ),
        ),
        TopicProposal(
            title="The Ethics of Non-Translation in Junot Díaz and Valeria Luiselli",
            research_question=(
                "How do Díaz's The Brief Wondrous Life of Oscar Wao and Luiselli's "
                "Lost Children Archive use strategic non-translation of Spanish to "
                "create zones of linguistic sovereignty within English-language narrative?"
            ),
            gap_description=(
                "The growing practice of 'untranslated' Spanish in Anglophone fiction "
                "has been noted but not rigorously compared across Dominican-American "
                "and Mexican-American literary traditions. The two authors deploy "
                "non-translation for distinct ethical and political purposes."
            ),
        ),
        TopicProposal(
            title="Pidgin Poetics: Linguistic Decolonization in Ken Saro-Wiwa and Gabriel Okara",
            research_question=(
                "How do Saro-Wiwa's Sozaboy and Okara's The Voice deploy English-Pidgin "
                "hybridization and Ijaw-calqued English as competing strategies of "
                "linguistic decolonization in Nigerian fiction?"
            ),
            gap_description=(
                "Nigerian literature's radical experiments with English have been "
                "studied individually, but no sustained comparative reading examines "
                "how Saro-Wiwa's rotten English and Okara's Ijaw-inflected prose "
                "propose fundamentally different models of decolonial literary language."
            ),
        ),
        TopicProposal(
            title="Translingual Autobiography: Vilém Flusser and Hélène Cixous's Multilingual Selves",
            research_question=(
                "How do Flusser's Czech-Portuguese-German-French philosophical "
                "autobiography and Cixous's Franco-Algerian-German Reveries model "
                "translingual selfhood as a literary form?"
            ),
            gap_description=(
                "Autobiography studies and translation studies rarely intersect. Flusser "
                "and Cixous both write from positions of multilingual exile but develop "
                "opposing models: Flusser embraces perpetual linguistic homelessness "
                "while Cixous seeks a maternal language beneath all acquired tongues."
            ),
        ),
        TopicProposal(
            title="Creole Continuum as Literary Device in Patrick Chamoiseau and Junot Díaz",
            research_question=(
                "How do Chamoiseau's French-Créole layering in Texaco and Díaz's "
                "English-Spanish-Spanglish in Oscar Wao construct competing models of "
                "the creole continuum as a narrative device?"
            ),
            gap_description=(
                "Caribbean creolization theory (Glissant, Bernabé) is rarely applied "
                "comparatively to Francophone and Anglophone/Hispanophone Caribbean "
                "fiction. Chamoiseau and Díaz embody different poles of the creole "
                "continuum with distinct formal consequences for narrative voice."
            ),
        ),
        TopicProposal(
            title="Machine Translation and Literary Opacity: Kenneth Goldsmith and Mette Moestrup's Conceptual Poetics",
            research_question=(
                "How do Goldsmith's English-language and Moestrup's Danish-language "
                "conceptual poetry engage machine translation as both medium and subject, "
                "testing the limits of algorithmic translatability?"
            ),
            gap_description=(
                "The literary implications of machine translation remain understudied "
                "in comparative literature. These two conceptual poets explicitly "
                "engage translation technology, but their approaches diverge: Goldsmith "
                "embraces informational flatness while Moestrup foregrounds what resists "
                "computational processing."
            ),
        ),
    ],
    1: [  # Trauma, Memory, and Poetic Form
        TopicProposal(
            title="Partition Poetics: Lyric Form in Faiz Ahmed Faiz and Amrita Pritam",
            research_question=(
                "How do Faiz's Urdu ghazals and Pritam's Punjabi lyrics develop "
                "distinct formal strategies to render the 1947 Partition's collective "
                "memory, and what does their comparison reveal about the relationship "
                "between poetic form and historical rupture?"
            ),
            gap_description=(
                "Partition literature is typically studied within single-language "
                "traditions. A comparative formal analysis of Urdu and Punjabi lyric "
                "responses to the same catastrophe — attending to metre, genre "
                "convention, and the politics of linguistic choice — is absent."
            ),
        ),
        TopicProposal(
            title="Postmemory Across the Armenian Diaspora: Balakian and Vosganian",
            research_question=(
                "How do Peter Balakian's Ozone Journal and Varujan Vosganian's "
                "Cartea şoaptelor transmit Armenian genocide memory across English "
                "and Romanian literary traditions, and what formal devices enable "
                "transgenerational transmission without direct testimony?"
            ),
            gap_description=(
                "Postmemory theory (Hirsch) was developed for European Jewish memory "
                "and has not been systematically tested against Armenian diaspora "
                "literature. The English-Romanian comparison opens a South-East European "
                "axis absent from postmemory scholarship."
            ),
        ),
        TopicProposal(
            title="Trauma and Musical Structure in Toni Morrison's Jazz and Xiaolu Guo's A Concise Chinese-English Dictionary for Lovers",
            research_question=(
                "How do Morrison and Guo deploy rhythmic fragmentation and structural "
                "improvisation as formal encodings of collective trauma — African-American "
                "and Cultural Revolution, respectively?"
            ),
            gap_description=(
                "Musical structure as narrative form has been studied in Morrison but "
                "not compared cross-culturally to Chinese experimental fiction. Both "
                "authors use musical principles (jazz, linguistic rhythm) to register "
                "trauma's disruption of linear narrative."
            ),
        ),
        TopicProposal(
            title="The Wound of Language: Pizarnik and Sexton's Lyric Strategies of Silence",
            research_question=(
                "How do Alejandra Pizarnik's Spanish and Anne Sexton's English "
                "confessional lyrics develop parallel strategies of repetition, "
                "fragmentation, and silence as formal responses to psychic trauma?"
            ),
            gap_description=(
                "These contemporary poets are studied in isolation within their "
                "national traditions. A comparative formal analysis of their shared "
                "strategies — the wound as linguistic event — would illuminate how "
                "confessional poetics operates across the Americas."
            ),
        ),
        TopicProposal(
            title="Deferred Testimony: Amnesia and Temporal Structure in Modiano and Bolaño",
            research_question=(
                "How do Patrick Modiano's Rue des Boutiques Obscures and Roberto "
                "Bolaño's Nocturno de Chile deploy unreliable temporal structure and "
                "narrative amnesia as formal embodiments of political trauma in Vichy "
                "France and Pinochet's Chile?"
            ),
            gap_description=(
                "Comparative studies of European and Latin American dictatorship "
                "literature rarely focus on narrative temporality. Both Modiano and "
                "Bolaño use amnesia as structural principle, but the political valence "
                "of forgetting differs radically across their contexts."
            ),
        ),
        TopicProposal(
            title="Documentary Poetics of State Violence: Claudia Rankine and M. NourbeSe Philip",
            research_question=(
                "How do Rankine's Citizen and Philip's Zong! transform archival "
                "and documentary material into poetic forms that register racial "
                "violence's accumulative structure?"
            ),
            gap_description=(
                "Both poets are individually prominent in contemporary poetics, "
                "but their distinct archival methods — Rankine's everyday micro-"
                "aggressions versus Philip's legal document deconstruction — have "
                "not been compared as competing models of documentary witnessing."
            ),
        ),
        TopicProposal(
            title="Embodied Memory in Post-Dictatorship Fiction: Diamela Eltit and Herta Müller",
            research_question=(
                "How do Eltit's Lumpérica and Müller's The Hunger Angel develop "
                "somatic prose styles — language inscribed on the body — as formal "
                "responses to state violence in Chile and Romania?"
            ),
            gap_description=(
                "Post-dictatorship literature in Latin America and Eastern Europe "
                "is rarely compared. Both Eltit and Müller foreground the body as "
                "the site where political violence becomes literary form, but their "
                "divergent aesthetic traditions produce different somatics of writing."
            ),
        ),
        TopicProposal(
            title="The Repetition Compulsion as Narrative Form in Kobo Abe and Juan Rulfo",
            research_question=(
                "How do Abe's The Woman in the Dunes and Rulfo's Pedro Páramo "
                "deploy temporal loops and spectral repetition to formalize "
                "collective trauma in Japanese and Mexican literary traditions?"
            ),
            gap_description=(
                "Both novels use cyclical, claustrophobic temporal structures, but "
                "no comparative study examines how repetition functions as traumatic "
                "form across these two non-Western modernist traditions. The gap "
                "between Japanese existential fiction and Mexican magical realism "
                "conceals shared formal strategies."
            ),
        ),
        TopicProposal(
            title="Intergenerational Silence in NoViolet Bulawayo and Viet Thanh Nguyen",
            research_question=(
                "How do Bulawayo's We Need New Names and Nguyen's The Sympathizer "
                "use childhood perspective and split consciousness to encode "
                "transgenerational political violence across Zimbabwean and "
                "Vietnamese diasporic experience?"
            ),
            gap_description=(
                "African and Asian diaspora literatures are almost never compared "
                "despite shared structural concerns: displacement, second-generation "
                "silence, dual consciousness. Both novels use formally innovative "
                "strategies to transmit trauma across generations and continents."
            ),
        ),
        TopicProposal(
            title="Singing the Disappeared: Testimonial Song-Poetics in Víctor Jara's Legacy and Mahmoud Darwish's Lyric",
            research_question=(
                "How do Chilean nueva canción (via Jara's posthumous reception) and "
                "Palestinian resistant poetry (Darwish) develop parallel song-based "
                "poetic forms to memorialize political disappearance?"
            ),
            gap_description=(
                "Latin American testimonio and Palestinian resistance poetry share "
                "the problem of memorializing the disappeared through lyric form, "
                "but no comparative study examines how musical and poetic structures "
                "encode political absence across these traditions."
            ),
        ),
    ],
    2: [  # Romanticism's Cross-Cultural Migrations
        TopicProposal(
            title="Hafez's Afterlives: Goethe's West-östlicher Divan and FitzGerald's Rubáiyát",
            research_question=(
                "How do Goethe's and FitzGerald's translations of Persian lyric poetry "
                "construct competing models of Romantic self-transcendence through "
                "Orientalist poetic modes?"
            ),
            gap_description=(
                "German and English Romantic receptions of Persian poetry are typically "
                "studied separately. A comparative analysis would show how the 'same' "
                "Persian sources generate fundamentally different Romantic aesthetics "
                "depending on the receiving literary system's needs."
            ),
        ),
        TopicProposal(
            title="The Creole Sublime: Romantic Categories in Heredia's Cuban and Bello's Venezuelan Poetry",
            research_question=(
                "How do José María Heredia and Andrés Bello rework Burke's and "
                "Kant's sublime to theorize New World landscapes as sites of "
                "anti-colonial literary identity in early 19C Latin American poetry?"
            ),
            gap_description=(
                "Latin American Romanticism is studied as derivative of European "
                "models. Heredia and Bello actively transform the sublime into a "
                "tool of creole emancipation — a creative appropriation that has "
                "not been analyzed through the lens of migrant aesthetics."
            ),
        ),
        TopicProposal(
            title="Herder's Volkslieder and Its Afterlives: Karadžić's Serbian and Lönnrot's Finnish Collections",
            research_question=(
                "How was Herder's Romantic folk-song theory creatively appropriated "
                "in Karadžić's Serbian and Lönnrot's Kalevala to produce competing "
                "national literary canons?"
            ),
            gap_description=(
                "Herder's influence on nation-building is acknowledged but never "
                "comparatively analyzed across South Slavic and Nordic contexts. "
                "These two receptions reveal how the same Romantic idea generates "
                "radically different institutional and literary outcomes."
            ),
        ),
        TopicProposal(
            title="The Gothic as Migrant Form: Ann Radcliffe's Italian Gothic and Kyoka Izumi's Supernatural Tales",
            research_question=(
                "How does the Gothic mode migrate from its British-Italian origins "
                "to Meiji-era Japan, and how does Izumi transform supernatural "
                "narrative to encode anxieties of modernization?"
            ),
            gap_description=(
                "Gothic studies remain Eurocentric. The migration of Gothic "
                "sensibility to Japan via Meiji literary modernization has been "
                "noted but not rigorously compared with the genre's European "
                "origins, testing whether 'the Gothic' is a portable category."
            ),
        ),
        TopicProposal(
            title="Sentimental Journeys: Rousseau's Julie and Qing Dynasty Literati Sentimental Fiction",
            research_question=(
                "How does the Romantic sentimental tradition encounter Chinese "
                "qing aesthetics in late-Qing literary translations and "
                "adaptations, and what hybrid forms result from this encounter?"
            ),
            gap_description=(
                "The encounter between European sentimentalism and Chinese "
                "sentimental fiction (the qing tradition from Dream of the Red "
                "Chamber onward) at the end of the Qing dynasty has been noted "
                "by historians of translation but not analyzed as a comparative "
                "literary phenomenon with formal consequences."
            ),
        ),
        TopicProposal(
            title="The Byronic Hero in Persian Modernity: Byron's Eastern Tales and Nimā Yushij's Modernism",
            research_question=(
                "How does the Byronic hero migrate from British Romantic poetry "
                "to early 20C Iranian literary modernism in Nimā Yushij's verse, "
                "and what transformations does this figure undergo in transit?"
            ),
            gap_description=(
                "Iranian literary modernism acknowledges European Romantic "
                "influence but has not examined the specific migration of the "
                "Byronic hero as a figure of rebellious subjectivity into "
                "Persian literary culture."
            ),
        ),
        TopicProposal(
            title="Romantic Ecology Before Ecology: Dorothy Wordsworth's Journals and Bashō's Oku no Hosomichi",
            research_question=(
                "How do Dorothy Wordsworth's walking journals and Bashō's poetic "
                "travelogue develop parallel phenomenologies of landscape attention "
                "that prefigure ecological consciousness across British Romantic "
                "and Edo Japanese literary traditions?"
            ),
            gap_description=(
                "Ecocriticism's historical genealogy is Eurocentric. A comparative "
                "reading of these two walking-writing practices would show how "
                "pre-ecological sensibility develops independently in traditions "
                "that cannot have influenced each other."
            ),
        ),
        TopicProposal(
            title="The Romantic Fragment in Arabic Modernity: Schlegel's Athenäum and Adonis's al-Thābit wa-l-mutaḥawwil",
            research_question=(
                "How does the Romantic fragment as theoretical form migrate from "
                "German idealism (Schlegel) to Arabic modernist poetics (Adonis), "
                "and what does this migration reveal about the fragment's claim "
                "to universality?"
            ),
            gap_description=(
                "Adonis's theoretical debt to German Romanticism is acknowledged "
                "but not analyzed formally. A comparative reading of the fragment "
                "as form across German and Arabic traditions would test whether "
                "the Romantic concept of productive incompletion operates differently "
                "in Arabic literary culture."
            ),
        ),
        TopicProposal(
            title="Blake's Prophetic Vision and Tagore's Gitanjali as Comparative Romantic Mysticism",
            research_question=(
                "How do William Blake and Rabindranath Tagore develop competing "
                "models of mystical-prophetic poetry that challenge Enlightenment "
                "rationalism from English and Bengali literary traditions?"
            ),
            gap_description=(
                "Blake and Tagore are individually central to their national "
                "Romantic canons but never compared. Both develop prophetic poetic "
                "modes against dominant rationalism, but their mysticisms arise "
                "from distinct religious and philosophical traditions."
            ),
        ),
        TopicProposal(
            title="Romanticism's Musical Turn: E.T.A. Hoffmann's Musical Tales and Higuchi Ichiyō's Lyric Prose",
            research_question=(
                "How do Hoffmann's and Ichiyō's prose styles deploy musical "
                "structure — rhythmic patterning, tonal modulation, thematic "
                "development — as narrative principles, and what does this "
                "comparison reveal about Romantic claims for music's supremacy "
                "among the arts?"
            ),
            gap_description=(
                "The Romantic privileging of music pervades both German and "
                "Japanese literary traditions but has never been compared "
                "as a cross-cultural formal phenomenon. Hoffmann and Ichiyō "
                "both subordinate prose to musical logic via distinct means."
            ),
        ),
    ],
    3: [  # Canon Formation, Institutional Power, and World Literature
        TopicProposal(
            title="The Nobel Effect: Prize Culture and Global Poetics in Mo Yan and Olga Tokarczuk",
            research_question=(
                "How does the Nobel Prize mediate the international reception "
                "of Chinese and Polish fiction, reshaping both the authors' "
                "domestic reputations and the construction of 'world literature' "
                "canons?"
            ),
            gap_description=(
                "Nobel Prize studies tend to focus on single laureates. "
                "A comparative analysis of how the same institutional mechanism "
                "operates on Chinese and Polish literary systems would reveal "
                "asymmetries in how prize culture constructs literary universality."
            ),
        ),
        TopicProposal(
            title="Cold War Canon Wars: The Congress for Cultural Freedom vs. Inostrannaya Literatura",
            research_question=(
                "How did the CIA's Congress for Cultural Freedom and the Soviet "
                "journal Inostrannaya Literatura construct competing canons of "
                "translated literature during the Cold War, and what literary "
                "values did their selections encode?"
            ),
            gap_description=(
                "Cultural Cold War studies document institutional histories but "
                "rarely perform close readings of the actual translated texts "
                "that circulated. A literary analysis of what was selected and "
                "excluded by both institutions would bridge the gap between "
                "institutional critique and textual analysis."
            ),
        ),
        TopicProposal(
            title="Translation Flows and Canon Asymmetry: Mishima in France vs. Sembène in the Anglophone Academy",
            research_question=(
                "How do the radically different reception economies of Japanese "
                "literature (via Mishima's French canonization) and Senegalese "
                "literature (via Sembène's Anglophone academic reception) reveal "
                "structural asymmetries in the world literary system?"
            ),
            gap_description=(
                "World literature theory often discusses asymmetry abstractly. "
                "A concrete comparative case study of how two non-Western authors "
                "are processed by different metropolitan literary systems would "
                "ground Casanova's 'literary world-system' in textual evidence."
            ),
        ),
        TopicProposal(
            title="Peripheral Modernisms and Belated Discovery: Lispector in Anglophone and Francophone Criticism",
            research_question=(
                "How does the belated 'discovery' of Clarice Lispector in "
                "Anglophone and Francophone literary criticism construct Latin "
                "American women's writing as perpetually 'new,' and what does "
                "this reveal about institutional asymmetries in literary canonization?"
            ),
            gap_description=(
                "Lispector's recent international canonization has been celebrated "
                "but not critically analyzed as an institutional phenomenon. "
                "Comparing her Anglophone and Francophone receptions reveals "
                "different gatekeeping mechanisms and marketing strategies."
            ),
        ),
        TopicProposal(
            title="Small Literatures and Big Canons: Kundera and Kadare as Peripheral Canon-Builders",
            research_question=(
                "How do Milan Kundera and Ismail Kadare theorize the European "
                "novel from semi-peripheral positions (Czech/Albanian), and what "
                "do their competing strategies of self-canonization reveal about "
                "how 'small nations' construct literary universality?"
            ),
            gap_description=(
                "Both Kundera and Kadare strategically position their national "
                "traditions within European literary history, but no comparison "
                "exists. Their distinct strategies — Kundera's essayistic novel "
                "theory vs. Kadare's mythic rewriting — illuminate competing "
                "models of peripheral canon-building."
            ),
        ),
        TopicProposal(
            title="Gate-Keeping the Avant-Garde: Tel Quel and Concretismo as Institutional Models",
            research_question=(
                "How did the French journal Tel Quel and the Brazilian Concretismo "
                "movement construct competing institutional models of literary "
                "innovation through editorial manifestos, translation programs, "
                "and international networking?"
            ),
            gap_description=(
                "French and Brazilian avant-gardes influenced each other but are "
                "studied separately. A comparative institutional analysis would "
                "reveal how metropolitan and peripheral avant-gardes build canons "
                "through radically different power-resource configurations."
            ),
        ),
        TopicProposal(
            title="Indigenous Anthologizing as Counter-Canon: Joy Harjo and Natasha Kanapé Fontaine",
            research_question=(
                "How do Indigenous editors and poets in Anglophone (Harjo) and "
                "Francophone (Kanapé Fontaine) North American traditions build "
                "alternative canons that resist absorption into settler literary "
                "institutions?"
            ),
            gap_description=(
                "Indigenous literary studies in English and French Canada/US are "
                "siloed. A comparative analysis of anthologizing strategies would "
                "reveal shared and divergent approaches to canon-building outside "
                "the settler literary establishment."
            ),
        ),
        TopicProposal(
            title="The Politics of the Untranslated: Aidoo and Raja Rao as Texts Resisting Canonization",
            research_question=(
                "How do Ama Ata Aidoo's Our Sister Killjoy and Raja Rao's "
                "Kanthapura encode in their formal strategies a resistance to "
                "the institutional circuits of 'world literature'?"
            ),
            gap_description=(
                "Ghanaian and Indian Anglophone fiction both engage the politics "
                "of English while resisting easy global circulation. No comparative "
                "study examines how these novels' formal choices — Aidoo's genre "
                "hybridity, Rao's Sanskritized English — function as deliberate "
                "refusals of canonical smoothness."
            ),
        ),
        TopicProposal(
            title="The Discovery Paradigm: Bolaño's Posthumous and Ferrante's Anonymous Canonization",
            research_question=(
                "How do Roberto Bolaño's posthumous canonization and Elena "
                "Ferrante's anonymous success function as case studies in "
                "contemporary canon formation, and what do these two models "
                "reveal about authorial presence and institutional mediation?"
            ),
            gap_description=(
                "Both Bolaño and Ferrante achieved global canonization under "
                "unusual circumstances (death and pseudonymity). No comparative "
                "study examines how the publishing apparatus constructs literary "
                "value precisely when authorial control is absent."
            ),
        ),
        TopicProposal(
            title="UNESCO's Representative Works: The Geopolitics of Literary Translation 1948-2005",
            research_question=(
                "How did UNESCO's Collection of Representative Works shape global "
                "literary canons through its translation program, and what "
                "geopolitical logics determined which literatures were deemed "
                "'representative'?"
            ),
            gap_description=(
                "UNESCO's translation program was the largest state-sponsored "
                "effort at canon construction in literary history, yet literary "
                "scholars have barely analyzed it. A study combining institutional "
                "analysis with close reading of prefatory materials would fill "
                "a major gap in world literature scholarship."
            ),
        ),
    ],
    4: [  # Formalism, Narratology, and Methodology
        TopicProposal(
            title="Bakhtin Beyond Dialogue: Testing Polyphony on Eileen Chang's Shanghai Fiction",
            research_question=(
                "How does Bakhtinian polyphony work — or fail — when applied to "
                "Eileen Chang's mid-century Shanghai fiction, and what does this "
                "test case reveal about the methodology's implicit cultural "
                "assumptions?"
            ),
            gap_description=(
                "Bakhtin's dialogism was developed for the Russian novel. Its "
                "applicability to Chinese modernist fiction — where polyphony "
                "arises from different linguistic and social conditions — has "
                "been asserted but never rigorously tested."
            ),
        ),
        TopicProposal(
            title="Genette's Narratology vs. Sōseki and Machado de Assis: Testing Structural Categories",
            research_question=(
                "How do structuralist narratological categories (Genette's Figures III) "
                "apply — or break down — when confronted with Natsume Sōseki's Kokoro "
                "and Machado de Assis's Memórias Póstumas de Brás Cubas?"
            ),
            gap_description=(
                "Narratology claims universal applicability but was developed "
                "from European texts. Testing its categories against Japanese "
                "and Brazilian modernist narrative forms would identify specific "
                "points where the methodology's Eurocentrism becomes visible."
            ),
        ),
        TopicProposal(
            title="Close Reading East and West: New Criticism and Chinese Shīhuà Traditions",
            research_question=(
                "How do Western close reading methods (Richards, Empson) and "
                "traditional Chinese shīhuà (poetry-talk) hermeneutics compare "
                "as interpretive methodologies, and what does each reveal about "
                "the other's blind spots?"
            ),
            gap_description=(
                "Comparative methodology is rarely reflexive about its own "
                "tools. A systematic comparison of these two close-reading "
                "traditions — both focused on textual detail but proceeding "
                "from different epistemological premises — would expose the "
                "cultural assumptions built into 'close reading' itself."
            ),
        ),
        TopicProposal(
            title="The Prague School's Forgotten Comparatism: Mukařovský and Translation Studies",
            research_question=(
                "How can Jan Mukařovský's structural aesthetics serve as a "
                "methodological bridge between Czech, Russian, and Western "
                "literary theory, and what would a Mukařovskian translation "
                "theory look like?"
            ),
            gap_description=(
                "Mukařovský is far less studied than Jakobson or Shklovsky "
                "in Anglophone theory. His concept of the aesthetic function "
                "as socially mediated offers a methodology that bridges "
                "formalism and sociology of literature in ways directly "
                "relevant to contemporary translation studies."
            ),
        ),
        TopicProposal(
            title="Affect Theory as Literary Method: Sedgwick and Ahmed Applied Comparatively",
            research_question=(
                "How does affect theory (Sedgwick's paranoid/reparative reading, "
                "Ahmed's cultural politics of emotion) transform the reading of "
                "contemporary fiction when applied comparatively across "
                "Anglophone and Francophone traditions?"
            ),
            gap_description=(
                "Affect theory has been applied within single-language literary "
                "studies but rarely tested as a comparative method. Applying "
                "the same affective-hermeneutic framework across English and "
                "French fiction would reveal whether 'affect' translates as "
                "a methodological category."
            ),
        ),
        TopicProposal(
            title="Distant Reading as Comparative Method: Topic Modeling 19C French and Russian Realism",
            research_question=(
                "How do computational methods (topic modeling, stylometry) expose "
                "or obscure cross-national literary patterns when applied to "
                "19C French and Russian realist corpora?"
            ),
            gap_description=(
                "Digital humanities promises to make comparison empirical, "
                "but its methods have not been rigorously tested on the "
                "classic comparatist terrain: cross-linguistic literary "
                "systems. A French-Russian realist corpus comparison would "
                "assess whether computational methods confirm, contradict, "
                "or simply bypass humanistic comparison."
            ),
        ),
        TopicProposal(
            title="Iser vs. Todorov: Phenomenological and Structuralist Hermeneutics Compared",
            research_question=(
                "How do Wolfgang Iser's reader-response theory and Tzvetan "
                "Todorov's structuralist poetics construct the reader and "
                "the reading act differently, and what are the consequences "
                "for comparative literary interpretation?"
            ),
            gap_description=(
                "German phenomenological and French structuralist approaches "
                "to reading are taught as alternatives but rarely directly "
                "compared on the same texts. A rigorous comparison would "
                "clarify what each methodology makes visible and what it "
                "systematically obscures."
            ),
        ),
        TopicProposal(
            title="World Literature's Method Problem: Damrosch vs. Apter on Translatability",
            research_question=(
                "How do David Damrosch's circulation model and Emily Apter's "
                "untranslatability thesis produce competing methodologies for "
                "comparative literature, and can these be reconciled?"
            ),
            gap_description=(
                "The Damrosch-Apter debate is the central methodological "
                "impasse in contemporary comparative literature, yet it has "
                "been conducted primarily at the theoretical level. Testing "
                "both positions against specific multilingual literary objects "
                "would ground the debate in textual evidence."
            ),
        ),
        TopicProposal(
            title="Ecocriticism as Comparative Method: Morton and Heise Applied to Pacific and Nordic Climate Fiction",
            research_question=(
                "How do Timothy Morton's object-oriented ecology and Ursula "
                "Heise's sense of place framework generate different readings "
                "of Pacific Island and Nordic climate fiction?"
            ),
            gap_description=(
                "Ecocritical methodology has not been tested comparatively "
                "across radically different geographic literary traditions. "
                "Pacific Island and Nordic literatures share climate crisis "
                "as subject but occupy opposite positions in the global "
                "ecology, making their comparison a test case for ecocritical "
                "method's universality."
            ),
        ),
        TopicProposal(
            title="Montage as Cross-Media Method: Eisenstein's Film Theory and Döblin's Berlin Alexanderplatz",
            research_question=(
                "How does Eisenstein's theory of intellectual montage, when "
                "applied as a reading method to Döblin's Berlin Alexanderplatz, "
                "reveal narrative strategies invisible to conventional "
                "narratological analysis?"
            ),
            gap_description=(
                "Literary montage is acknowledged as a technique but rarely "
                "treated as a transferable analytical method. Applying "
                "Eisenstein's cinematic montage theory systematically to "
                "Döblin's novel would test whether cross-media methodology "
                "generates genuinely new literary-critical insights."
            ),
        ),
    ],
    5: [  # Postcolonial / Decolonial Critique
        TopicProposal(
            title="The Plantation as World-System: Cuban Testimonio and Mauritian Créole Fiction",
            research_question=(
                "How do Miguel Barnet's Biografía de un cimarrón and Ananda "
                "Devi's Ève de ses décombres encode colonial plantation violence "
                "across Caribbean and Indian Ocean literary traditions?"
            ),
            gap_description=(
                "Plantation literature studies focus on the Atlantic. Comparing "
                "Cuban testimonio and Mauritian Créole fiction would reveal how "
                "the plantation as economic form generates distinct but "
                "structurally analogous literary responses across oceans."
            ),
        ),
        TopicProposal(
            title="Indigenous Futurism vs. Afrofuturism: Cherie Dimaline and Nnedi Okofor",
            research_question=(
                "How do Dimaline's The Marrow Thieves and Okofor's Binti "
                "develop competing decolonial speculative imaginaries from "
                "Indigenous Canadian and Nigerian-American traditions?"
            ),
            gap_description=(
                "Indigenous Futurism and Afrofuturism are studied separately "
                "despite shared decolonial commitments. A comparative reading "
                "would reveal how different colonial histories generate distinct "
                "speculative strategies for imagining non-colonial futures."
            ),
        ),
        TopicProposal(
            title="Fanon Beyond Fanon: Pepetela's Mayombe and Ouologuem's Le Devoir de violence",
            research_question=(
                "How do Pepetela and Ouologuem creatively appropriate and "
                "contest Fanonian anti-colonial theory in Angolan and Malian "
                "fiction, and what do their divergences reveal about Fanon's "
                "limits as literary-theoretical framework?"
            ),
            gap_description=(
                "Fanon's influence on African literature is asserted but "
                "rarely analyzed as a specifically literary phenomenon. "
                "Comparing how Lusophone and Francophone African novelists "
                "rewrite Fanon would test whether his theory survives "
                "the transition from political manifesto to novelistic form."
            ),
        ),
        TopicProposal(
            title="Settler Colonialism and Literary Witness: Coetzee's Disgrace and Kim Scott's Benang",
            research_question=(
                "How do J.M. Coetzee and Kim Scott confront the settler's "
                "impossible ethical position through formal experimentation "
                "in South African and Australian fiction?"
            ),
            gap_description=(
                "Settler-colonial literary studies are dominated by "
                "single-nation approaches. A South Africa-Australia "
                "comparison would reveal whether settler-colonial literature "
                "develops parallel formal strategies despite vastly different "
                "colonial histories and Indigenous literary traditions."
            ),
        ),
        TopicProposal(
            title="Cartographies of Displacement: Barghouti's I Saw Ramallah and Khoury's Gate of the Sun",
            research_question=(
                "How do Mourid Barghouti and Elias Khoury map Palestinian "
                "displacement through narrative form, and how do their "
                "competing cartographic strategies — the memoir and the "
                "polyphonic novel — construct different literary geographies?"
            ),
            gap_description=(
                "Palestinian literature is underrepresented in comparative "
                "literary studies. Comparing a Palestinian poet's memoir "
                "with a Lebanese novelist's epic reconstruction would "
                "illuminate how different genres and national positions "
                "generate distinct literary cartographies of the same "
                "dispossession."
            ),
        ),
        TopicProposal(
            title="The Indian Ocean as Literary World-System: Amitav Ghosh and Abdulrazak Gurnah",
            research_question=(
                "How do Ghosh's In an Antique Land and Gurnah's By the Sea "
                "use Indian Ocean trade routes to challenge nation-based "
                "models of literary comparison?"
            ),
            gap_description=(
                "Postcolonial comparison remains organized by colonial "
                "metropole (Anglophone, Francophone). The Indian Ocean "
                "as a literary framework connecting South Asia and East "
                "Africa is theoretically proposed but rarely demonstrated "
                "through sustained comparative close reading."
            ),
        ),
        TopicProposal(
            title="Creolization as Literary Theory: Chamoiseau's Texaco and Wilson Harris's Palace of the Peacock",
            research_question=(
                "How do Chamoiseau and Harris develop créolité and cross-"
                "culturalism as competing Caribbean decolonial aesthetics, "
                "and what do their formal differences reveal about "
                "Francophone and Anglophone Caribbean literary divergences?"
            ),
            gap_description=(
                "Caribbean literary theory (Glissant, Brathwaite) bridges "
                "linguistic boundaries, but Francophone and Anglophone "
                "Caribbean novels are rarely compared formally. Chamoiseau "
                "and Harris represent the richest test case for whether "
                "creolization produces comparable formal strategies across "
                "Caribbean language traditions."
            ),
        ),
        TopicProposal(
            title="The Bildungsroman in Neocolonial Africa: Dangarembga and Cheikh Hamidou Kane",
            research_question=(
                "How do Tsitsi Dangarembga's Nervous Conditions and Cheikh "
                "Hamidou Kane's L'Aventure ambiguë expose the violence of "
                "colonial education by subverting the European Bildungsroman "
                "form from Anglophone Zimbabwean and Francophone Senegalese "
                "positions?"
            ),
            gap_description=(
                "The African Bildungsroman is acknowledged as a counter-genre "
                "but rarely compared across Anglophone and Francophone traditions. "
                "Dangarembga's and Kane's novels both use colonial education "
                "as narrative engine while arriving at formally distinct "
                "conclusions about the possibility of African self-formation."
            ),
        ),
        TopicProposal(
            title="Southern Epistemologies in Literary Practice: Mia Couto and Subcomandante Marcos",
            research_question=(
                "How do Mia Couto's Terra Sonâmbula and Subcomandante Marcos's "
                "Zapatista communiqués embody Boaventura de Sousa Santos's "
                "'epistemologies of the South' through literary form?"
            ),
            gap_description=(
                "Southern theory (Santos) proposes epistemological alternatives "
                "to Northern universalism but rarely identifies literary "
                "embodiments. Comparing Mozambican experimental fiction and "
                "Mexican revolutionary narrative would ground the theory in "
                "comparative textual analysis."
            ),
        ),
        TopicProposal(
            title="The Subaltern Writes Back: Mahasweta Devi and Rigoberta Menchú's Testimonial Forms",
            research_question=(
                "How do Mahasweta Devi's Pterodactyl and Rigoberta Menchú's "
                "testimonio navigate between oral testimony and written literary "
                "form in Indian and Guatemalan subaltern traditions?"
            ),
            gap_description=(
                "Subaltern studies and testimonio theory developed independently "
                "in South Asian and Latin American contexts. A comparative "
                "formal analysis of how these two traditions mediate between "
                "oral witness and written literature would test whether "
                "'subalternity' generates comparable literary strategies."
            ),
        ),
    ],
    6: [  # Gender, Sexuality, and Embodiment
        TopicProposal(
            title="Non-Binary Embodiment in Medieval Romance: The Roman de Silence and the Saga of Hervör",
            research_question=(
                "How do Old French and Old Norse narratives of gender disguise "
                "construct non-binary subjectivities that exceed modern binary "
                "frameworks?"
            ),
            gap_description=(
                "Medieval gender studies typically operate within single-language "
                "traditions. Comparing the Roman de Silence and the Saga of Hervör "
                "would reveal how two distinct medieval literary systems handle "
                "gender transgression through narrative form, without anachronistically "
                "imposing contemporary gender categories."
            ),
        ),
        TopicProposal(
            title="Queer Temporalities: Yourcenar's Alexis and Forster's Maurice",
            research_question=(
                "How do Marguerite Yourcenar's Alexis ou le Traité du vain "
                "combat and E.M. Forster's Maurice develop formal strategies "
                "of temporal delay and indirection to represent homosexual "
                "disclosure in early 20C French and English fiction?"
            ),
            gap_description=(
                "Both novels were written in the early 20C but published "
                "under very different conditions. No comparison exists of "
                "how French and English literary systems shaped the formal "
                "strategies available for representing same-sex desire."
            ),
        ),
        TopicProposal(
            title="Trans Poetics: Paul B. Preciado's Testo Junkie and Akwaeke Emezi's Freshwater",
            research_question=(
                "How do Preciado and Emezi develop linguistic-somatic forms "
                "that destabilize gendered embodiment across Franco-Spanish "
                "theory-memoir and Nigerian-American fiction?"
            ),
            gap_description=(
                "Trans literary studies is emerging but lacks comparative "
                "frameworks. Preciado's pharmaceutical auto-experimentation "
                "and Emezi's Igbo cosmological model represent radically "
                "different approaches to trans embodiment in literature, "
                "neither reducible to the other."
            ),
        ),
        TopicProposal(
            title="Sappho's Afterlives: Anne Carson's If Not, Winter and Renée Vivien's Translations",
            research_question=(
                "How do Carson's and Vivien's competing Sappho translations "
                "construct distinct feminist poetics across modernist and "
                "contemporary periods?"
            ),
            gap_description=(
                "Sappho translation is a rich site for feminist literary "
                "theory but has not been compared across periods. Carson's "
                "minimalist fragmentation and Vivien's decadent completion "
                "represent opposing feminist strategies for reclaiming a "
                "canonical queer woman's voice."
            ),
        ),
        TopicProposal(
            title="Maternal Horror and the Gothic Body: Shirley Jackson and Mariana Enriquez",
            research_question=(
                "How do Jackson's We Have Always Lived in the Castle and "
                "Enriquez's Las cosas que perdimos en el fuego deploy "
                "feminine bodily horror as feminist critique in American "
                "and Argentine Gothic fiction?"
            ),
            gap_description=(
                "Women's Gothic fiction is studied within national traditions. "
                "A US-Argentine comparison would reveal how different "
                "political contexts (Cold War domesticity, post-dictatorship "
                "violence) generate distinct forms of gendered horror."
            ),
        ),
        TopicProposal(
            title="Masculinity in Crisis: Murakami's Norwegian Wood and Houellebecq's Extension du domaine de la lutte",
            research_question=(
                "How do Haruki Murakami and Michel Houellebecq formally "
                "encode masculine crisis in late-capitalist modernity "
                "through competing narrative strategies?"
            ),
            gap_description=(
                "Both are bestselling novelists of male melancholia but "
                "have never been compared. Their distinct approaches — "
                "Murakami's nostalgic lyrical realism vs. Houellebecq's "
                "sociological provocation — reveal how Japanese and "
                "French literary cultures construct masculine subjectivity "
                "in crisis differently."
            ),
        ),
        TopicProposal(
            title="The Spinster as Literary Figure: Barbara Pym and Clarice Lispector",
            research_question=(
                "How do Pym's Excellent Women and Lispector's A Hora da "
                "Estrela revalue the figure of the unmarried woman against "
                "marriage-plot conventions in British and Brazilian fiction?"
            ),
            gap_description=(
                "The 'spinster narrative' has been studied within British "
                "fiction but not compared internationally. Lispector's "
                "radical formal experimentation and Pym's ironic realism "
                "represent opposing literary strategies for the same "
                "feminist project: dignifying the unmarried woman."
            ),
        ),
        TopicProposal(
            title="Embodied Resistance: The Dancing Body in Arundhati Roy and Jamaica Kincaid",
            research_question=(
                "How do Roy's The God of Small Things and Kincaid's Lucy "
                "deploy the female body in motion as resistance to both "
                "patriarchal and colonial disciplinary regimes?"
            ),
            gap_description=(
                "Indian and Caribbean women's fiction share the problem of "
                "representing the female body under multiple oppressions. "
                "Both Roy and Kincaid use dance, physical movement, and "
                "bodily sensation as formal elements, but the political "
                "registers of their embodied poetics differ."
            ),
        ),
        TopicProposal(
            title="Drag and Literary Performance: Manuel Puig and Reinaldo Arenas",
            research_question=(
                "How do Puig's El beso de la mujer araña and Arenas's "
                "Antes que anochezca deploy camp, drag, and performative "
                "gender as narrative strategies that challenge heteronormative "
                "literary form in Argentine and Cuban fiction?"
            ),
            gap_description=(
                "Both are canonical queer Latin American writers but are "
                "rarely compared. Their distinct uses of performance — "
                "Puig's cinematic melodrama vs. Arenas's picaresque excess — "
                "represent competing models of queer literary politics under "
                "authoritarian regimes."
            ),
        ),
        TopicProposal(
            title="Pregnancy as Narrative Form: Jenny Offill's Dept. of Speculation and Annie Ernaux's L'Événement",
            research_question=(
                "How do Offill and Ernaux use pregnancy and its interruption "
                "as structural principles that reorganize novelistic time, "
                "voice, and selfhood in American and French autofiction?"
            ),
            gap_description=(
                "Reproductive experience as a formal literary device — not "
                "merely as subject matter — is understudied. Comparing these "
                "two fragmentary narratives would reveal how the pregnant or "
                "post-pregnant body generates distinct temporal and narrative "
                "structures in US and French literary traditions."
            ),
        ),
    ],
    7: [  # Far-Right Narratives and Political Aesthetics
        TopicProposal(
            title="Nostalgia as Political Weapon: Camus's Le Grand Remplacement and Raspail's Le Camp des Saints",
            research_question=(
                "How do Renaud Camus's essayistic manifesto and Jean Raspail's "
                "apocalyptic novel construct competing models of civilizational "
                "decline narrative in French far-right literary production?"
            ),
            gap_description=(
                "The literary strategies of the French far right are dismissed "
                "as mere propaganda. A formal analysis of how Camus's and "
                "Raspail's texts construct their rhetorical worlds would reveal "
                "genuinely literary mechanisms of political seduction that "
                "criticism must understand in order to counter."
            ),
        ),
        TopicProposal(
            title="Authoritarian Realism vs. Dystopian Counter-Narrative: Prilepin and Glukhovsky",
            research_question=(
                "How do Zakhar Prilepin's pro-Kremlin war fiction and Dmitry "
                "Glukhovsky's Metro 2033 dystopia construct competing visions "
                "of Russian political community through opposed narrative "
                "aesthetics?"
            ),
            gap_description=(
                "Contemporary Russian literature's political aesthetics are "
                "understudied in comparative literature. Prilepin's martial "
                "realism and Glukhovsky's speculative dystopia represent "
                "the two poles of Russian political fiction, but their "
                "formal opposition has not been analyzed as a literary system."
            ),
        ),
        TopicProposal(
            title="Anti-Totalitarian Allegory: Orwell's Animal Farm and Kadare's The Palace of Dreams",
            research_question=(
                "How do Orwell and Kadare develop allegorical forms to "
                "critique authoritarian power across British and Albanian "
                "literary traditions, and what formal possibilities does "
                "allegory offer for political satire under different "
                "censorship regimes?"
            ),
            gap_description=(
                "Orwell is canonically anti-totalitarian; Kadare wrote "
                "under an actual dictatorship. Comparing how allegory "
                "functions under freedom (as warning) vs. under censorship "
                "(as disguised critique) would reveal the form's political "
                "versatility."
            ),
        ),
        TopicProposal(
            title="The Eco-Fascist Imagination: Linkola's Can Life Prevail? and Hamsun's Growth of the Soil",
            research_question=(
                "How do Pentti Linkola and Knut Hamsun develop ecological "
                "literary visions with authoritarian undercurrents, and what "
                "does their comparison reveal about the structural complicity "
                "between eco-utopianism and far-right ideology in Nordic "
                "literary traditions?"
            ),
            gap_description=(
                "Ecocriticism avoids engaging with ecological writing that "
                "harbors authoritarian politics. A frank comparative analysis "
                "of Finnish and Norwegian eco-authoritarian literary traditions "
                "would expose a blind spot in ecocritical methodology."
            ),
        ),
        TopicProposal(
            title="Counter-Hegemonic Satire: Jelinek's Die Kinder der Toten and Saviano's Gomorra",
            research_question=(
                "How do Elfriede Jelinek and Roberto Saviano deploy different "
                "formal strategies — linguistic excess and documentary realism — "
                "to counter far-right populism in Austrian and Italian "
                "literary contexts?"
            ),
            gap_description=(
                "Literary resistance to populist nationalism is studied "
                "within single national traditions. Comparing Jelinek's "
                "maximalist linguistic deconstruction with Saviano's "
                "investigative realism reveals competing formal strategies "
                "for the same political project."
            ),
        ),
        TopicProposal(
            title="Conspiracy as Narrative Form: Umberto Eco's The Prague Cemetery and DeLillo's Libra",
            research_question=(
                "How do Eco and DeLillo formally reconstruct conspiracy "
                "theory as narrative structure, and what does fiction's "
                "capacity to anatomize conspiratorial thinking reveal "
                "about the aesthetics of political paranoia?"
            ),
            gap_description=(
                "Conspiracy fiction is a recognized genre but lacks "
                "comparative formal analysis. Eco's historical pastiche "
                "and DeLillo's documentary fiction represent competing "
                "models for how the novel can represent — and potentially "
                "inoculate against — conspiratorial epistemology."
            ),
        ),
        TopicProposal(
            title="Diagnosing Authoritarian Longing: Krasznahorkai's Sátántangó and Pamuk's Snow",
            research_question=(
                "How do László Krasznahorkai and Orhan Pamuk use formal "
                "strategies — hypnotic prose, nested metafiction — to "
                "diagnose the aesthetic seductions of nationalism in "
                "Hungarian and Turkish fiction?"
            ),
            gap_description=(
                "Both novelists write from increasingly authoritarian states "
                "and both anatomize authoritarian desire rather than simply "
                "opposing it. No comparison exists of how Hungarian and "
                "Turkish literature formally represents the seductive "
                "structure of nationalist ideology."
            ),
        ),
        TopicProposal(
            title="The Novel as Post-Fascist Memory: Cercas's Anatomy of a Moment and Lobo Antunes's The Return of the Caravels",
            research_question=(
                "How do Javier Cercas and António Lobo Antunes formally "
                "confront the legacy of Francoism and Salazarism through "
                "competing narrative strategies in Spanish and Portuguese "
                "fiction?"
            ),
            gap_description=(
                "Iberian post-fascist literature is studied within single "
                "national traditions despite shared historical conditions. "
                "Cercas's documentary realism and Lobo Antunes's baroque "
                "modernism represent competing formal approaches to the "
                "same problem: remembering fascism after democracy."
            ),
        ),
        TopicProposal(
            title="Digital Pamphlet and Futurist Manifesto: Online Far-Right Aesthetics and Their Literary Antecedents",
            research_question=(
                "How does contemporary far-right digital literary production "
                "(manifestos, meme-fiction, accelerationist texts) draw on "
                "and transform the formal strategies of historical avant-garde "
                "manifestos, particularly Marinetti's Futurism?"
            ),
            gap_description=(
                "The aesthetic dimension of far-right online culture is "
                "studied by media scholars but not by literary critics. "
                "Tracing the formal continuity between Futurist manifestos "
                "and contemporary digital pamphlets would reveal how "
                "avant-garde aesthetic strategies migrate to authoritarian "
                "political projects."
            ),
        ),
        TopicProposal(
            title="Literary Populism: Handke's Late Fiction and Alexievich's Polyphonic Documentary",
            research_question=(
                "How do Peter Handke and Svetlana Alexievich construct "
                "'the people' as literary subject through opposed formal "
                "choices — Handke's pastoral lyricism vs. Alexievich's "
                "testimonial polyphony — in competing models of European "
                "political writing?"
            ),
            gap_description=(
                "The Handke-Alexievich contrast (both Nobel laureates) "
                "crystallizes a fundamental question about literary "
                "populism: whether 'the people' is better served by "
                "aesthetic contemplation or documentary witness. No "
                "comparative study has examined their opposed politics "
                "of literary form."
            ),
        ),
    ],
}


# ---------------------------------------------------------------------------
# Studied authors/works table (for frontend "Already Studied" panel)
# ---------------------------------------------------------------------------

CORPUS_STUDIED = [
    {"author": "Paul Celan", "works": ["Holocaust poetry", "Negative poetics"], "studied_by": "Daniel Feldman (2014)"},
    {"author": "Dan Pagis", "works": ["Holocaust poetry", "Testimonial silence"], "studied_by": "Feldman (2014), Yacobi (2005)"},
    {"author": "Rosario Ferré", "works": ["Self-translation (English/Spanish)", "Cannibalized language"], "studied_by": "Olga Blomgren (2025)"},
    {"author": "Édouard Glissant", "works": ["Translation as Relation"], "studied_by": "Sandra Bermann (2014)"},
    {"author": "Lawrence Durrell", "works": ["Orientalism in the Alexandria Quartet"], "studied_by": "James Gifford (1999)"},
    {"author": "Joseph Conrad", "works": ['"Amy Foster"', '"Prince Roman"', "Polish-English language politics"], "studied_by": "Juliette Bretan (2025)"},
    {"author": "Henry Highland Garnet", "works": ["Abolitionist orations", "Black Romanticism"], "studied_by": "Charline Jao (2025)"},
    {"author": "H.L.V. Derozio & Kasiprasad Ghosh", "works": ["Anglo-Indian Persianate poetry"], "studied_by": "Humberto Garcia (2025)"},
    {"author": "Edward Said", "works": ["Freud and the Non-European", "Orientalism"], "studied_by": "Khanna, Edelman, Mukherjee, Reilly, Al-Kassim (2025)"},
    {"author": "Gayatri Chakravorty Spivak", "works": ["Death of a Discipline", "Planetarity"], "studied_by": "Khanna/Spivak conversation (2025)"},
    {"author": "Nazım Hikmet", "works": ["Poetry in China", "Bandung/Asiafrica solidarity"], "studied_by": "Alice Xiang (2025)"},
    {"author": "Ricardo Aleixo & Arthur Bispo do Rosário", "works": ["Brazilian concretism", "Black Brazilian poetics"], "studied_by": "Jane Kassavin (2025)"},
    {"author": "Jean Métellus", "works": ["Anacaona (historical drama)"], "studied_by": "Xavier Lee (2025)"},
    {"author": "Aphra Behn", "works": ["Oroonoko: The Royal Slave"], "studied_by": "Xavier Lee (2025)"},
    {"author": "Joan Anim-Addo", "works": ["Imoinda (opera adaptation)"], "studied_by": "Xavier Lee (2025)"},
    {"author": "Sulaiman Addonia", "works": ["Silence Is My Mother Tongue"], "studied_by": "Akshya Saxena (2025)"},
    {"author": "Jacinta Kerketta", "works": ["Angor (Embers)"], "studied_by": "Akshya Saxena (2025)"},
    {"author": "Shakespeare", "works": ["Measure for Measure", "Falstaff / Henry IV"], "studied_by": "Braider (2025), Deutermann (2025)"},
    {"author": "Ovid / Guillaume de Lorris / Jean de Meun", "works": ["Roman de la Rose", "Metamorphoses (Pygmalion)"], "studied_by": "Hicks-Bartlett (2025)"},
    {"author": "William Gardner Smith", "works": ["The Stone Face"], "studied_by": "Nyawalo (2025)"},
    {"author": "Futabatei Shimei", "works": ["Ukigumo (Floating Cloud)"], "studied_by": "Bonnie Pang (2025)"},
    {"author": "Intan Paramaditha", "works": ["Gentayangan"], "studied_by": "Jennifer Goodlander (2025)"},
    {"author": "Virginia Woolf", "works": ["Between the Acts"], "studied_by": "Tianyi Shou (2025)"},
    {"author": "Xiao Hong", "works": ["Hulan He Zhuan (Tales of Hulan River)"], "studied_by": "Tianyi Shou (2025)"},
    {"author": "Theresa Hak Kyung Cha", "works": ["White Dust from Mongolia"], "studied_by": "Vero Chai (2025)"},
    {"author": "Cervantes", "works": ["Don Quixote (Romantic approach)"], "studied_by": "Gilbert-Santamaria (2025)"},
    {"author": "Francisco Balagtas", "works": ["Florante at Laura"], "studied_by": "Kelly (2025)"},
    {"author": "Mao Zedong", "works": ["Classicist poetry / fake Mao poems"], "studied_by": "Zhiyi Yang (2025)"},
    {"author": "Henry David Thoreau", "works": ["Walden (gender & ecology)"], "studied_by": "Rachael DeWitt (2025)"},
    {"author": "Chaucer", "works": ["The Franklin's Tale (Dorigen)"], "studied_by": "Bartlett & Crocker (2025)"},
    {"author": "James Baldwin", "works": ["Go Tell It on the Mountain", "Another Country"], "studied_by": "Mikko Tuhkanen (2025)"},
    {"author": "Omar El Akkad", "works": ["American War"], "studied_by": "Lydia R. Cooper (2025)"},
    {"author": "Jorge Isaacs", "works": ["María (Romantic hero, Colombia)"], "studied_by": "Mercedes Lopez Rodriguez (2025)"},
    {"author": "Viktor Shklovsky", "works": ["Theory of parody", "Italian reception", "Formalism"], "studied_by": "Lipovetsky, Tripiccione, Kalinin (2025)"},
    {"author": "Yuri Tynianov", "works": ["Literary evolution theory"], "studied_by": "Oushakine (2025)"},
    {"author": "Kazimir Malevich & Velimir Khlebnikov", "works": ["Futurism/Formalism", "Linguistic aesthetics"], "studied_by": "Dennis Ioffe (2025)"},
    {"author": "Flaubert", "works": ["Novembre", "Madame Bovary (gender)"], "studied_by": "Bélanger/Brassard (2025)"},
    {"author": "Rachilde", "works": ["Monsieur Vénus"], "studied_by": "Elinor Knutsen (2025)"},
    {"author": "Georges Rodenbach", "works": ["Bruges-la-Morte"], "studied_by": "Elinor Knutsen (2025)"},
    {"author": "George Sand", "works": ["Indiana", '"La Marquise"'], "studied_by": "Sophie Ménard (2025)"},
    {"author": "Émile Zola", "works": ["La Curée (lesbianism)"], "studied_by": "Shauna Heck (2025)"},
    {"author": "Jane de la Vaudère", "works": ["Les Demi-sexes"], "studied_by": "Islert (2025), Clère (2025)"},
    {"author": "Georges Eekhoud", "works": ["L'Autre vue (homosexuality)"], "studied_by": "Grommerch (2025)"},
    {"author": "Baudelaire", "works": ["Le Spleen de Paris (satire)"], "studied_by": "Patrick Thériault (2025)"},
    {"author": "Olivier Cadiot / Pierre Alferi", "works": ["Revue de littérature générale (montage)"], "studied_by": "Huppe (2025), Wourm (2025)"},
    {"author": "Grégory Chatonsky", "works": ["Internes (GPT co-written)"], "studied_by": "Yves Citton (2025)"},
    {"author": "Sophie Divry, Sandra Lucbert, Nathalie Quintane", "works": ["Satirical montage"], "studied_by": "Saint-Amand (2025), Quintane (2025)"},
    {"author": "Karoline Georges", "works": ["Posthuman fiction"], "studied_by": "Laura Lafrance (2025)"},
    {"author": "P.K. Dick", "works": ['"The Golden Man"'], "studied_by": "Manuela Mohr (2025)"},
    {"author": "Alain Damasio", "works": ["Les Furtifs"], "studied_by": "Julien Tribotté (2025)"},
    {"author": "Kole Omotoso", "works": ["The Combat"], "studied_by": "Verissimo (2025)"},
    {"author": "Aslı Erdoğan", "works": ["The City in Crimson Cloak"], "studied_by": "Ali Kulez (2025)"},
    {"author": "May Ayim & Ada Diagne", "works": ["Black German poetry"], "studied_by": "Adrienne Merritt (2025)"},
    {"author": "Lydie Salvayre", "works": ["Pas Pleurer (Cry, Mother Spain)"], "studied_by": "Mats Haraldsen (2025)"},
    {"author": "B. Kucinski", "works": ["A nova ordem", "O colapso da nova ordem"], "studied_by": "Georg Wink (2026)"},
    {"author": "Francesca Melandri", "works": ["Sangue giusto"], "studied_by": "Guido Bartolini (2026)"},
    {"author": "Ricardo M. Rojas", "works": ["El señor Robinson"], "studied_by": "Patrick Eser (2026)"},
    {"author": "Lauren Slater", "works": ["Lying (fictionality)"], "studied_by": "Mengchen Lang (2025)"},
    {"author": "Charles Yu", "works": ["How to Live Safely in a Science Fictional Universe"], "studied_by": "Daniel Punday (2025)"},
    {"author": "Willy Schumann", "works": ["Being Present (Hitler Youth memoir)"], "studied_by": "Anne Rothe (2009)"},
    {"author": "Ry Nikonova", "works": ["Samizdat journals Nomer/Transponans"], "studied_by": "Rebekah Smith (2025)"},
    {"author": "Marianne Hirsch", "works": ["Postmemory theory"], "studied_by": "Hirsch (2008) — self-authored"},
    {"author": "Marie-Pier Lafontaine", "works": ["Chienne (post-traumatic)"], "studied_by": "Gabriel Proulx (2025)"},
    {"author": "Félicité de Choiseul-Meuse", "works": ["Julie, ou j'ai sauvé ma rose"], "studied_by": "Mélissa Thiriot (2025)"},
    {"author": "Don't Look Up (2021 film)", "works": ["Satirical metapolitics"], "studied_by": "Stefanie Schäfer (2026)"},
    {"author": "Wordsworth", "works": ["Peter Bell (via Bateson)"], "studied_by": "Ramsey McGlazer (2025)"},
    {"author": "Huang Gongwang", "works": ["Dwelling in the Fuchun Mountains (scroll painting)"], "studied_by": "Chloe Estep (2025)"},
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Seed 8 directions + 80 topics into DB")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB")
    args = parser.parse_args()

    db = Database()
    db.initialize()

    if args.dry_run:
        print("=== DRY RUN — no DB changes ===\n")
        for i, d in enumerate(DIRECTIONS):
            topics = TOPICS_BY_DIRECTION[i]
            print(f"Direction {i + 1}: {d.title}")
            print(f"  Tensions: {d.dominant_tensions}")
            print(f"  Mediators: {d.dominant_mediators}")
            print(f"  Scale: {d.dominant_scale} | Gap: {d.dominant_gap}")
            print(f"  Papers: {len(d.paper_ids)}")
            print(f"  Topics ({len(topics)}):")
            for t in topics:
                print(f"    - {t.title}")
            print()

        print(f"\nCorpus Studied: {len(CORPUS_STUDIED)} entries")
        print("\nTotal: 8 directions, 80 topics")
        return

    # Step 1: Clear existing directions and topics
    print("Clearing existing directions and topics...")
    db.delete_all_directions_and_topics()

    # Step 2: Insert directions
    print("Inserting 8 directions...")
    direction_ids = []
    for i, direction in enumerate(DIRECTIONS):
        dir_id = db.insert_direction(direction)
        direction.id = dir_id
        direction_ids.append(dir_id)
        print(f"  [{i + 1}] {direction.title} -> {dir_id}")

    # Step 3: Insert topics
    print("\nInserting 80 topics...")
    for dir_idx, dir_id in enumerate(direction_ids):
        topics = TOPICS_BY_DIRECTION[dir_idx]
        direction = DIRECTIONS[dir_idx]
        topic_ids = []
        for topic in topics:
            topic.direction_id = dir_id
            topic.evidence_paper_ids = direction.paper_ids[:5]  # Link to first 5 papers
            topic.target_journals = ["Comparative Literature"]
            tid = db.insert_topic(topic)
            topic_ids.append(tid)

        # Update direction with topic_ids
        direction.topic_ids = topic_ids
        db.insert_direction(direction)
        print(f"  Direction {dir_idx + 1}: {len(topics)} topics inserted")

    print(f"\nDone! 8 directions and 80 topics seeded into {db.db_path}")


if __name__ == "__main__":
    main()
