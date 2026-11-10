"""Which wiki and which page categories make up each series. Pure configuration.

To add a series: add an entry to SERIES. Category names come from the wiki
(e.g. https://kimetsu-no-yaiba.fandom.com/wiki/Category:Episodes).
"""

import re
from dataclasses import dataclass


# Category name meaning "every article of the wiki". Listed last, it collects only the pages no
# earlier category claimed: small wikis leave many pages uncategorised.
ALL_ARTICLES = "*"
# Pages the catch-all skips: sub-pages ("Sung Jinwoo/Gallery") and list pages.
NOT_ARTICLES = r"/|^list of|^lists? |gallery|^\d{4}$"


@dataclass(frozen=True)
class CategorySource:
    """One kind of page and the wiki category listing those pages.

    Used by: application/collect.py  CollectService.collect()
    """

    kind: str  # our name for the page type, also the folder name under data/raw/<series>/
    category: str  # wiki category title, without the "Category:" prefix
    include_subcategories: bool = False  # e.g. Characters -> Demons, Hashira, ...
    # Keep only pages whose infobox matches, for wikis that mix several series in one category
    # (Naruto's "Episodes" holds Naruto, Shippuden and Boruto). (field, regex) pairs, all must
    # fully match, case-insensitive; a missing field counts as "".
    where: tuple[tuple[str, str], ...] = ()
    # (field, lowest, highest): keep pages whose infobox number is in range (chapters 1-244).
    number_between: tuple[str, int, int] | None = None
    # Skip pages whose title matches (case-insensitive), for categories without an infobox flag
    # to filter on (Naruto's "Movies" also lists "Boruto: Naruto the Movie").
    exclude_titles: str = ""
    # Explicit page titles, used instead of the category's members: important pages the wiki
    # never categorised (Dragon Ball: "Majin Buu", "Dragon Balls", "Tournament of Power").
    titles: tuple[str, ...] = ()
    # Semantic MediaWiki properties to store as facts: (wiki property, our fact name) pairs.
    properties: tuple[tuple[str, str], ...] = ()

    def accepts(self, infobox: dict[str, str]) -> bool:
        """Whether a page with this infobox belongs to the series (always True without filters).

        Called by: application/collect.py  CollectService.collect()
        """
        for key, pattern in self.where:
            if not re.fullmatch(pattern, infobox.get(key, "").strip(), re.I):
                return False
        if self.number_between:
            key, low, high = self.number_between
            m = re.match(r"\s*(\d+)", infobox.get(key, ""))
            if not m or not low <= int(m.group(1)) <= high:
                return False
        return True


@dataclass(frozen=True)
class SeriesSource:
    """Where a series' knowledge comes from.

    Used by: application/collect.py  CollectService.collect()
             scripts/collect.py      (lists the valid --series choices)
    """

    id: str  # our id, e.g. "demon_slayer"
    title: str  # display name
    wiki_host: str  # fandom wiki host name
    categories: tuple[CategorySource, ...]
    # A sequel sharing its world with another series (Shippuden -> Naruto): characters, jutsu
    # and places are indexed once, under that series, and searched for both.
    shares_with: str | None = None


def search_scope(series: str | None) -> str | tuple[str, ...] | None:
    """The series ids a question about `series` searches: itself plus the one it shares
    pages with ("naruto_shippuden" -> ("naruto_shippuden", "naruto")). None = everything.

    Called by: application/retrieve.py  RetrievalService.retrieve()
    """
    source = SERIES.get(series) if series else None
    if source and source.shares_with:
        return (series, source.shares_with)
    return series


# naruto.fandom.com infobox flags that separate the original series from Boruto and spin-offs.
_NARUTO_ANIME = (("boruto", "no|"), ("boruto anime", "no|"))
_NARUTO_MANGA = (("boruto", "no|"), ("blue vortex", "no|"), ("v jump", "no|"), ("sasuke retsuden", "no|"),
                 ("konoha shinden", "no|"))

_NARUTO_CHARACTER_FACTS = (("Parent", "parents"), ("Affiliation", "affiliation"), ("Clan", "clan"),
                           ("Classification", "classification"), ("Ninja_Rank", "rank"),
                           ("Species", "species"), ("Status", "status"))

SERIES: dict[str, SeriesSource] = {
    "demon_slayer": SeriesSource(
        id="demon_slayer",
        title="Demon Slayer: Kimetsu no Yaiba",
        wiki_host="kimetsu-no-yaiba.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters", include_subcategories=True),
            CategorySource("arc", "Story Arcs"),
            CategorySource("breathing_style", "Breathing Styles"),
            CategorySource("location", "Locations"),
        ),
    ),
    "death_note": SeriesSource(
        id="death_note",
        title="Death Note",
        wiki_host="deathnote.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Manga chapters"),
            CategorySource("character", "Manga characters"),
            CategorySource("character", "Anime characters"),
            CategorySource("character", "Shinigami"),
            CategorySource("death_note", "Death Notes"),
            CategorySource("location", "Locations"),
            CategorySource("organization", "Organizations"),
        ),
    ),
    "attack_on_titan": SeriesSource(
        id="attack_on_titan",
        title="Attack on Titan",
        wiki_host="attackontitan.fandom.com",
        categories=(
            # The wiki keeps separate anime versions of most pages ("Characters (Anime)") and
            # spin-off pages (Junior High, Before the Fall...): the main manga pages are used.
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Attack on Titan Chapters"),
            CategorySource("character", "Characters"),
            CategorySource("titan", "Titans"),
            CategorySource("location", "Locations"),
            CategorySource("organization", "Organizations"),
            CategorySource("arc", "Arcs"),
        ),
    ),
    "jujutsu_kaisen": SeriesSource(
        id="jujutsu_kaisen",
        title="Jujutsu Kaisen",
        wiki_host="jujutsu-kaisen.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            # "Characters" lists the main cast directly; its subcategories are only re-groupings
            # (by gender, by occupation...) except Cursed Spirits, which are added explicitly.
            CategorySource("character", "Characters"),
            CategorySource("character", "Cursed Spirits", include_subcategories=True),
            # Innate / extension / non-innate techniques and shikigami are subcategories.
            CategorySource("technique", "Cursed Techniques", include_subcategories=True),
            CategorySource("technique", "Domain Expansions"),
            # Two levels down (Innate -> Inherited), so not reached by include_subcategories:
            # Limitless, Ten Shadows, Blood Manipulation...
            CategorySource("technique", "Inherited Techniques"),
            CategorySource("technique", "Maximum Techniques"),
            # Core concepts (Cursed Energy, Binding Vow, Six Eyes...) and story events.
            CategorySource("concept", "Terminology"),
            CategorySource("concept", "Jujutsu"),
            CategorySource("event", "Events", include_subcategories=True),
            CategorySource("object", "Cursed Objects", include_subcategories=True),
            CategorySource("object", "Cursed Tools"),
            CategorySource("location", "Locations"),
            CategorySource("organization", "Organizations"),
            CategorySource("arc", "Story Arcs"),
        ),
    ),
    # naruto.fandom.com covers Naruto, Shippuden and Boruto in the same flat categories; each
    # episode/chapter infobox says which series it belongs to. Characters, jutsu and places are
    # shared: they are indexed once, under "naruto", and Shippuden questions search them too.
    "naruto": SeriesSource(
        id="naruto",
        title="Naruto",
        wiki_host="naruto.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", where=_NARUTO_ANIME + (("shippuden", "no"),)),
            CategorySource("chapter", "Chapters", where=_NARUTO_MANGA, number_between=("chapter", 1, 244)),
            # Character pages show an empty {{Infobox}}: the data is in Semantic MediaWiki.
            CategorySource("character", "Characters", properties=_NARUTO_CHARACTER_FACTS),
            CategorySource("jutsu", "Kekkei Genkai"),
            CategorySource("jutsu", "Jutsu"),
            CategorySource("clan", "Clans"),
            CategorySource("location", "Locations", include_subcategories=True),
            CategorySource("organization", "Teams"),  # Akatsuki, Team 7, Anbu...
            CategorySource("concept", "Naruto Terms"),  # Tailed Beast, chakra...
            CategorySource("concept", "Ninja Ranks"),  # Chūnin Exams, Hokage...
            CategorySource("event", "Battles"),  # Fourth Shinobi World War...
            # Movies (The Last, Road to Ninja...) and OVAs; Boruto's are a different series.
            CategorySource("movie", "Movies", exclude_titles=r"^boruto"),
            CategorySource("ova", "OVA", exclude_titles=r"^boruto"),
            CategorySource("arc", "Arcs"),
        ),
    ),
    "naruto_shippuden": SeriesSource(
        id="naruto_shippuden",
        title="Naruto Shippuden",
        wiki_host="naruto.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", where=_NARUTO_ANIME + (("shippuden", "yes"),)),
            # Part II of the manga (Shippuden's story) starts at chapter 245.
            CategorySource("chapter", "Chapters", where=_NARUTO_MANGA, number_between=("chapter", 245, 700)),
        ),
        shares_with="naruto",
    ),
    # onepiece.fandom.com has no flat Episodes/Chapters/Characters lists: pages sit one level
    # down (Season 1..22, "<Arc> Chapters"), and characters are listed by gender (canon only;
    # non-canon characters are in separate subcategories, deliberately not included).
    "one_piece": SeriesSource(
        id="one_piece",
        title="One Piece",
        wiki_host="onepiece.fandom.com",
        categories=(
            CategorySource("episode", "Episodes by Season", include_subcategories=True),
            CategorySource("chapter", "Chapters by Arc", include_subcategories=True),
            CategorySource("character", "Male Characters"),
            CategorySource("character", "Female Characters"),
            CategorySource("character", "Transgender Characters"),
            CategorySource("devil_fruit", "Devil Fruits"),
            CategorySource("devil_fruit", "Paramecia"),
            CategorySource("devil_fruit", "Logia"),
            CategorySource("devil_fruit", "Zoan", include_subcategories=True),
            CategorySource("organization", "Pirate Groups"),
            # Crews are listed under group categories: Straw Hat Pirates, Beasts Pirates...
            CategorySource("organization", "Four Emperors Groups", include_subcategories=True),
            CategorySource("organization", "Seven Warlords of the Sea Groups"),
            CategorySource("organization", "Three Great Powers"),
            CategorySource("organization", "World Government Groups"),
            CategorySource("concept", "Terms"),
            CategorySource("concept", "History"),
            CategorySource("concept", "Fighting Styles"),
            CategorySource("concept", "Artifacts"),
            CategorySource("arc", "Story Arcs"),
        ),
    ),
    "vinland_saga": SeriesSource(
        id="vinland_saga",
        title="Vinland Saga",
        wiki_host="vinlandsaga.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters"),
            CategorySource("location", "Locations"),
            CategorySource("arc", "Story Arcs"),
            # Groups like the Jomsvikings have no category: everything else, as "page".
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES),
        ),
    ),
    "solo_leveling": SeriesSource(
        id="solo_leveling",
        title="Solo Leveling",
        wiki_host="solo-leveling.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("chapter", "Chapters by Story Arcs", include_subcategories=True),
            CategorySource("character", "Male"),
            CategorySource("character", "Female"),
            CategorySource("character", "Monarchs"),
            CategorySource("character", "Shadows"),
            CategorySource("character", "Hunters"),
            CategorySource("ability", "Abilities"),
            CategorySource("object", "Items"),
            CategorySource("race", "Races", include_subcategories=True),
            CategorySource("organization", "Organizations"),
            CategorySource("organization", "Guilds"),
            CategorySource("location", "Locations", include_subcategories=True),
            CategorySource("arc", "Arcs"),
            # Many pages (Beru, Antares, the System) have no category at all.
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES),
        ),
    ),
    "hunter_x_hunter": SeriesSource(
        id="hunter_x_hunter",
        title="Hunter x Hunter",
        wiki_host="hunterxhunter.fandom.com",
        categories=(
            # The 2011 anime only: the 1999 one would give a second "episode 1".
            CategorySource("episode", "List of Episodes (2011 series)"),
            CategorySource("chapter", "Chapters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Male characters"),
            CategorySource("character", "Female characters"),
            CategorySource("character", "Chimera Ants"),  # Neferpitou: no gender category
            CategorySource("organization", "Group"),  # Phantom Troupe, Zoldyck Family, Hunter Association
            CategorySource("concept", "Terms"),  # Nen, Hunter Code...
            CategorySource("concept", "Fighting Styles"),
            CategorySource("object", "Items"),
            CategorySource("location", "Locations"),
            CategorySource("arc", "Arcs"),
        ),
    ),
    "black_clover": SeriesSource(
        id="black_clover",
        title="Black Clover",
        wiki_host="blackclover.fandom.com",
        categories=(
            CategorySource("episode", "Episodes by Arc", include_subcategories=True),
            CategorySource("chapter", "Chapters by Arc", include_subcategories=True),
            CategorySource("chapter", "Chapters"),  # the newest chapters are not filed by arc yet
            CategorySource("character", "Male Characters"),
            CategorySource("character", "Female Characters"),
            CategorySource("character", "Devils", include_subcategories=True),
            CategorySource("magic", "Magic"),
            CategorySource("magic", "Magic Attributes"),
            CategorySource("concept", "Terminologies"),
            CategorySource("object", "Items"),
            CategorySource("location", "Kingdoms"),
            CategorySource("location", "Grand Magic Zones"),
            CategorySource("location", "Clover Kingdom Locations", include_subcategories=True),
            CategorySource("arc", "Arcs"),
            # Squads (Black Bulls, Golden Dawn) and spells have no category of their own.
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES),
        ),
    ),
    # dragonball.fandom.com covers every series. Like Naruto: characters, techniques and places
    # are indexed once under "dragon_ball"; each anime keeps its own episodes ("episode 1" of Z
    # is not episode 1 of Super), filtered on the episode infobox's "Series" field (written "GT" or "DBGT", "DBS" or
    # "Dragon Ball Super"...: every spelling is accepted).
    "dragon_ball": SeriesSource(
        id="dragon_ball",
        title="Dragon Ball",
        wiki_host="dragonball.fandom.com",
        categories=(
            CategorySource("episode", "Dragon Ball episodes", where=(("series", "db|dragon ball"),), exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Dragon Ball chapters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("transformation", "Transformations", include_subcategories=True, exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Techniques", exclude_titles=NOT_ARTICLES),
            CategorySource("race", "Races", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Planets", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Sagas", include_subcategories=True, exclude_titles=NOT_ARTICLES),
            CategorySource("movie", "Films", include_subcategories=True, exclude_titles=NOT_ARTICLES + r"|^template:"),
            # Key pages the wiki left without a category.
            CategorySource("concept", "uncategorised key pages", titles=(
                "Majin Buu", "Dragon Ball (object)", "Tournament of Power", "Autonomous Ultra Instinct (ability)",
                "Super Dragon Balls", "Black Star Dragon Ball", "Senzu Bean", "Potara", "Fusion Dance",
                "Hyperbolic Time Chamber", "Ki", "Saiyan Power", "Capsule Corporation", "Red Ribbon Army",
                "World Martial Arts Tournament", "Cell Games", "Tournament of Destroyers", "Multiverse",
                "Gods of Destruction", "Supreme Kai", "Zeno", "Perfected Ultra Instinct", "Saiyan Army", "Frieza Force",
                "Galactic Patrol", "Z Fighters", "Ginyu Force", "Universe 7", "Universe 6", "Time Patrol")),
        ),
    ),
    "dragon_ball_z": SeriesSource(
        id="dragon_ball_z",
        title="Dragon Ball Z",
        wiki_host="dragonball.fandom.com",
        categories=(
            CategorySource("episode", "Dragon Ball Z episodes", where=(("series", "dbz|dragon ball z"),), exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Dragon Ball Z chapters", exclude_titles=NOT_ARTICLES),
        ),
        shares_with="dragon_ball",
    ),
    "dragon_ball_gt": SeriesSource(
        id="dragon_ball_gt",
        title="Dragon Ball GT",
        wiki_host="dragonball.fandom.com",
        categories=(
            CategorySource("episode", "Dragon Ball GT episodes", where=(("series", "dbgt|gt|dragon ball gt"),), exclude_titles=NOT_ARTICLES),
        ),
        shares_with="dragon_ball",
    ),
    "dragon_ball_super": SeriesSource(
        id="dragon_ball_super",
        title="Dragon Ball Super",
        wiki_host="dragonball.fandom.com",
        categories=(
            CategorySource("episode", "Dragon Ball Super episodes", where=(("series", "dbs|dragon ball super"),), exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Dragon Ball Super manga chapters", exclude_titles=NOT_ARTICLES),
        ),
        shares_with="dragon_ball",
    ),
    "dragon_ball_daima": SeriesSource(
        id="dragon_ball_daima",
        title="Dragon Ball Daima",
        wiki_host="dragonball.fandom.com",
        categories=(
            CategorySource("episode", "Dragon Ball Daima episodes", where=(("series", "dbd|dragon ball daima"),), exclude_titles=NOT_ARTICLES),
        ),
        shares_with="dragon_ball",
    ),
    "chainsaw_man": SeriesSource(
        id="chainsaw_man",
        title="Chainsaw Man",
        wiki_host="chainsaw-man.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters"),
            CategorySource("devil", "Devils", include_subcategories=True),
            CategorySource("organization", "Groups"),
            CategorySource("concept", "Terminology"),
            CategorySource("location", "Locations"),
            CategorySource("arc", "Story Arcs"),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES),
        ),
    ),
    "spy_x_family": SeriesSource(
        id="spy_x_family",
        title="Spy x Family",
        wiki_host="spy-x-family.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters"),
            CategorySource("organization", "Organizations", include_subcategories=True),
            CategorySource("location", "Locations", include_subcategories=True),
            CategorySource("arc", "Story Arcs"),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES),
        ),
    ),
    "fullmetal_alchemist": SeriesSource(
        id="fullmetal_alchemist",
        title="Fullmetal Alchemist",
        wiki_host="fma.fandom.com",
        categories=(
            # Brotherhood (2009) follows the manga; the 2003 anime would give a second "episode 1".
            # Only 10 of its 64 episode pages are in the Brotherhood category: listed by title.
            CategorySource("episode", "Brotherhood episodes",
                           titles=tuple(f"Episode {n} (2009 Anime)" for n in range(1, 65))),
            CategorySource("chapter", "Chapters", exclude_titles=NOT_ARTICLES + r"|^chapters and volumes"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Alchemy", include_subcategories=True),
            CategorySource("object", "Items", include_subcategories=True),
            CategorySource("location", "Locations", include_subcategories=True),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|\(2003|live action"),
        ),
    ),
}
