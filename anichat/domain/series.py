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
NOT_ARTICLES = r"/|^list of|^lists? |gallery|^\d{4}$|^category:|^template:|^user:"


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
    # Skip pages that are members of these categories (Tokyo Revengers: the mobile game's event
    # pages have no common title pattern, but all are in "Pazuribe Events").
    exclude_categories: tuple[str, ...] = ()
    # Split each page into one page per section whose heading matches this regex (groups:
    # number, name): Bleach's volume pages hold their chapters as sections. See domain/sections.py.
    split_sections: str = ""
    # Keep only pages linked from this category's pages: the MCU wiki has 9,000 characters, but
    # the ones linked from the movie pages are the ones the movies are about.
    linked_from: str = ""
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

# Pages every wiki has that answer no question about the story (catch-all "page" sources).
WIKI_NOISE = (r"|^community:|^user:|^board thread:| wiki:|^volume \d|soundtrack|^blu-ray|popularity poll|"
              r"^(chapters|episodes|characters|episode guide|episode list|story arcs|locations)$|^chapters and volumes$")
NOISE_CATEGORIES = ("Music", "Songs", "Video Games", "Games", "Merchandise")


def standard_series(id: str, title: str, wiki_host: str, *extra: CategorySource, skip: str = "",
                    shares_with: str | None = None) -> SeriesSource:
    """A series on a wiki with the usual layout: pages titled exactly "Chapter N" / "Episode N"
    (spin-offs like "Chapter 1 (Holidays)" or "Reboot: Chapter 1" are left out, so numbers are
    unique), and the usual Characters / Locations / Organizations / Story Arcs categories (a
    missing one lists nothing). `extra`: wiki-specific sources, collected before the catch-all;
    `skip`: more title patterns (regex) to leave out of the catch-all.

    Called by: SERIES below
    """
    return SeriesSource(
        id=id, title=title, wiki_host=wiki_host, shares_with=shares_with,
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!episode \d+$)"),
            CategorySource("chapter", "Chapters", exclude_titles=r"^(?!chapter \d+$)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Arcs", exclude_titles=NOT_ARTICLES),
            *extra,
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + (f"|{skip}" if skip else ""),
                           exclude_categories=NOISE_CATEGORIES),
        ),
    )


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
    "my_hero_academia": SeriesSource(
        id="my_hero_academia",
        title="My Hero Academia",
        wiki_host="myheroacademia.fandom.com",
        categories=(
            # The spin-off Vigilantes has its own "Chapter 1" and "Episode 1": left out for now.
            CategorySource("episode", "Episodes", exclude_titles=r"\(vigilantes\)"),
            CategorySource("chapter", "Chapters", exclude_titles=r"\(vigilantes\)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("quirk", "Quirks", exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Ultimate Moves", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Battles", exclude_titles=NOT_ARTICLES),
            # Character pages keep relationships on a subpage ("Izuku Midoriya/Relationships").
            CategorySource("relationships", "Character Subpage", exclude_titles=r"^(?!.*/relationships$)"),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|\(vigilantes\)|soundtrack|^volume \d|^episodes$|^chapters and volumes$"),
        ),
    ),
    "frieren": SeriesSource(
        id="frieren",
        title="Frieren: Beyond Journey's End",
        wiki_host="frieren.fandom.com",
        categories=(
            CategorySource("episode", "Episodes"),
            CategorySource("chapter", "Chapters"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            # Character pages are tabbed: history, synopsis and relationships are subpages, not all
            # of them categorised. So: every subpage ("Frieren/History", "List of Characters/Minor").
            CategorySource("character_story", ALL_ARTICLES, exclude_titles=r"^[^/]*$|/gallery$"),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|^chapters and volumes$|^episodes and volumes$|"
                           r"^community:|^discord$|^blu-ray|^art works|^coloring book"),
        ),
    ),
    "one_punch_man": SeriesSource(
        id="one_punch_man",
        title="One Punch Man",
        wiki_host="onepunchman.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!episode \d+$)"),
            CategorySource("ova", "Episodes", exclude_titles=r"^(?!ova \d+$)"),
            # "Chapter 157 (Online)" is the Jump+ numbering of the same manga chapters: one is enough.
            # Named bonus chapters ("200 Yen") have no number: they are collected as pages below.
            CategorySource("chapter", "Chapters", exclude_titles=r"\(online\)|^(?!chapter \d)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            # Big organizations are subpages here ("Heroes/Hero Association"): subpages allowed.
            CategorySource("organization", "Organizations", exclude_titles=r"^list of|gallery"),
            CategorySource("arc", "Arcs", exclude_titles=NOT_ARTICLES + r"|^user:"),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Fights", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|\(online\)|^volume \d|^community:|"
                           r"popularity poll|^chapters and volumes$|^dvd$|^figures$|^audiobooks$|merchandise",
                           exclude_categories=("Games", "Music", "Polls")),
        ),
    ),
    "tokyo_revengers": SeriesSource(
        id="tokyo_revengers",
        title="Tokyo Revengers",
        wiki_host="tokyorevengers.fandom.com",
        categories=(
            # Spin-offs ("Chapter 1 (Todai Revengers)", "... (Letter from Keisuke Baji)") are left out:
            # they would give a second "chapter 1".
            CategorySource("episode", "Episodes", exclude_titles=r"\("),
            CategorySource("chapter", "Chapters", exclude_titles=r"\("),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            # Character pages keep relationships and story on subpages ("Manjiro Sano/Synopsis").
            CategorySource("relationships", "Relationships"),
            CategorySource("character_story", "Synopsis"),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Battles", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|\(todai revengers\)|"
                           r"\(letter from keisuke baji\)|^volume \d|^community:|^blu-ray|chibi revengers|"
                           r"^decisive battle|popularity poll|^calendar$",
                           exclude_categories=("Pazuribe Events", "Media", "Music", "Games", "Chibi Revengers Episodes")),
        ),
    ),
    "mob_psycho_100": SeriesSource(
        id="mob_psycho_100",
        title="Mob Psycho 100",
        wiki_host="mob-psycho-100.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!episode \d+$)"),
            CategorySource("chapter", "Chapters", exclude_titles=r"^(?!chapter \d)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES + r"|^template:|^characters$|^\?+$"),
            CategorySource("organization", "Claw", exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Psychic Techniques", exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Non-Psychic Techniques", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            # The live-action drama has its own episodes and characters: left out.
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|live-action|soundtrack|^community:|"
                           r"^(chapters|episodes|characters|humans|espers|games|anime|anime interviews|story arcs|"
                           r"mob psycho 100 wiki|lol)$|\(reigen\)|guide book|fanbook|picture collection|"
                           r"psychic battle|psychic puzzle|^sekai oni|hito kui|cherri bomb",
                           exclude_categories=("Live-action episodes", "Songs")),
        ),
    ),
    "fairy_tail": SeriesSource(
        id="fairy_tail",
        title="Fairy Tail",
        wiki_host="fairytail.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!episode \d+$)"),
            # The sequel (100 Years Quest) has its own chapter/episode 1: a separate series below.
            CategorySource("chapter", "Chapters", exclude_titles=r"^(?!chapter \d+$)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("magic", "Caster Magic", exclude_titles=NOT_ARTICLES),
            CategorySource("magic", "Holder Magic", exclude_titles=NOT_ARTICLES),
            CategorySource("magic", "Lost Magic", exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Spells", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Guilds", include_subcategories=True, exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Magic Items", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Fights", exclude_titles=NOT_ARTICLES + r"|^template:"),
            CategorySource("event", "Event", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + r"|^community:|^volume \d|soundtrack|"
                           r"chapter review|^fairy tail: 100 years quest chapter|^ft100yq episode",
                           exclude_categories=("Music", "Video Games")),
        ),
    ),
    "fairy_tail_100_years_quest": SeriesSource(
        id="fairy_tail_100_years_quest",
        title="Fairy Tail: 100 Years Quest",
        wiki_host="fairytail.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!ft100yq episode \d+$)"),
            CategorySource("chapter", "Fairy Tail: 100 Years Quest Chapters", exclude_titles=NOT_ARTICLES),
        ),
        shares_with="fairy_tail",
    ),
    # Wikis with the usual layout (see standard_series above).
    "blue_lock": standard_series("blue_lock", "Blue Lock", "bluelock.fandom.com"),
    "tokyo_ghoul": standard_series(
        "tokyo_ghoul", "Tokyo Ghoul", "tokyoghoul.fandom.com",
        # The sequel's "Re: Chapter N" pages: the tokyo_ghoul_re series below.
        skip=r"^re: (chapter|episode)|^jack: chapter|remake$"),
    "tokyo_ghoul_re": SeriesSource(
        id="tokyo_ghoul_re",
        title="Tokyo Ghoul:re",
        wiki_host="tokyoghoul.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!re: episode \d+$)"),
            CategorySource("chapter", "Chapters", exclude_titles=r"^(?!re: chapter \d+$)"),
        ),
        shares_with="tokyo_ghoul",
    ),
    "dr_stone": standard_series("dr_stone", "Dr. Stone", "dr-stone.fandom.com", skip=r"^reboot: chapter"),
    "hells_paradise": standard_series("hells_paradise", "Hell's Paradise", "jigokuraku.fandom.com"),
    "dandadan": standard_series("dandadan", "Dandadan", "dandadan.fandom.com"),
    "sakamoto_days": standard_series("sakamoto_days", "Sakamoto Days", "sakamoto-days.fandom.com",
                                     skip=r"\(holidays\)"),
    "fire_force": standard_series("fire_force", "Fire Force", "fireforce.fandom.com"),
    "haikyuu": SeriesSource(
        id="haikyuu",
        title="Haikyu!!",
        wiki_host="haikyuu.fandom.com",
        categories=(
            # Chapters are titled by name; the number is in the infobox ("chapter number = 1").
            # The category also holds volumes, a poll and one character page.
            CategorySource("chapter", "Chapters", exclude_titles=NOT_ARTICLES + r"|^category:|one-shot|\(volume\)|"
                           r"volumes$|\(manga\)$|popularity poll|^michiko umezawa$"),
            # Episode pages carry no episode number (only the adapted chapter): searchable by
            # name, not as "episode 5".
            CategorySource("anime_episode", "Episodes", exclude_titles=NOT_ARTICLES + r"|^category:|^episode guide$"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|\(volume\)|volumes$|"
                           r"^hyper projection play", exclude_categories=NOISE_CATEGORIES),
        ),
    ),
    # Episodes are numbered per season (R2 restarts at 1): one series per season.
    "code_geass": SeriesSource(
        id="code_geass",
        title="Code Geass: Lelouch of the Rebellion",
        wiki_host="codegeass.fandom.com",
        categories=(
            # Episode 1 uses another template without "season": no season counts as season 1.
            CategorySource("episode", "Episodes", where=(("season", "1|"),),
                           exclude_titles=r"^episode list$|of mask \(episode\)$|of the mask \(episode\)$"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Knightmare Frames", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Battles", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            # Theme-song artists have uncategorised pages: left out by name.
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|\(episode\)$|^(access \(axs\)|"
                           r"ali project|flow|jinn|orange range|sunset swish)$",
                           exclude_categories=NOISE_CATEGORIES + ("Voice actors", "Themes")),
        ),
    ),
    "code_geass_r2": SeriesSource(
        id="code_geass_r2",
        title="Code Geass R2",
        wiki_host="codegeass.fandom.com",
        categories=(CategorySource("episode", "Episodes", where=(("season", "2"),)),),
        shares_with="code_geass",
    ),
    "bleach": SeriesSource(
        id="bleach",
        title="Bleach",
        wiki_host="bleach.fandom.com",
        categories=(
            # Episodes are titled by name; the infobox has "episodenumber" (1-366, TYBW from 367).
            CategorySource("episode", "Episodes", exclude_titles=NOT_ARTICLES + r"|^episodes$"),
            # No chapter pages: each volume page holds its chapters as "=== 116. Name ===" sections.
            CategorySource("chapter", "Volumes", exclude_titles=NOT_ARTICLES + r"|^volumes$",
                           split_sections=r"(-?\d+)\.\s*(.+)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Zanpakutō", exclude_titles=NOT_ARTICLES),
            CategorySource("technique", "Techniques", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Important Terms", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Items", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Fights", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|\(disambiguation\)",
                           exclude_categories=NOISE_CATEGORIES + ("Watercooler", "Wikia Chat logs", "Volumes",
                                                                  "Chapters", "Disambiguation")),
        ),
    ),
    "seven_deadly_sins": standard_series(
        "seven_deadly_sins", "The Seven Deadly Sins", "nanatsu-no-taizai.fandom.com",
        # Later seasons number episodes per season ("Dragon's Judgement Episode 1"); the sequel
        # Four Knights of the Apocalypse has its own "Chapter 1 (4KOA)": both left out.
        skip=r"\(4koa\)|four knights|episode \d+$"),
    "kaiju_no_8": standard_series("kaiju_no_8", "Kaiju No. 8", "kaiju-no-8.fandom.com"),
    "oshi_no_ko": standard_series("oshi_no_ko", "Oshi no Ko", "oshinoko.fandom.com", skip=r"^interlude chapter"),
    "re_zero": standard_series("re_zero", "Re:Zero - Starting Life in Another World", "rezero.fandom.com"),
    "bungo_stray_dogs": standard_series("bungo_stray_dogs", "Bungo Stray Dogs", "bungostraydogs.fandom.com",
                                        skip=r"^beast chapter|^wan! "),
    # Light-novel series: episodes are numbered per season or titled by name, so they are kept as
    # unnumbered "anime_episode" pages (found by name, not as "episode 5").
    "sword_art_online": SeriesSource(
        id="sword_art_online",
        title="Sword Art Online",
        wiki_host="swordartonline.fandom.com",
        categories=(
            CategorySource("anime_episode", "Anime Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Terminology", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Objects", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|sword art offline|"
                           r"^sword art online wiki$",
                           exclude_categories=NOISE_CATEGORIES + ("Discography", "Lyrics", "Song", "Creator Publications",
                                                                  "Manga Volumes", "Light Novel Volumes",
                                                                  "Video Game Adaptation", "Non-Canon")),
        ),
    ),
    "tensura": SeriesSource(
        id="tensura",
        title="That Time I Got Reincarnated as a Slime",
        wiki_host="tensura.fandom.com",
        categories=(
            CategorySource("anime_episode", "Anime episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("ability", "Unique skills", exclude_titles=NOT_ARTICLES),
            CategorySource("ability", "Extra skills", exclude_titles=NOT_ARTICLES),
            CategorySource("race", "Species", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Groups", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Terminology", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|volume|^collaborations",
                           exclude_categories=NOISE_CATEGORIES + ("Manga Chapters", "Episode Galleries",
                                                                  "Character Galleries")),
        ),
    ),
    "overlord": SeriesSource(
        id="overlord",
        title="Overlord",
        wiki_host="overlordmaruyama.fandom.com",
        categories=(
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES,
                           exclude_categories=("Mass for the Dead Characters",)),
            CategorySource("organization", "Groups and Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("race", "Races", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Terminology", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("event", "Events", exclude_titles=NOT_ARTICLES, exclude_categories=("Mass for the Dead Events",)),
            CategorySource("object", "Items", exclude_titles=NOT_ARTICLES, exclude_categories=("Mass for the Dead Items",)),
            # The mobile game Mass for the Dead has its own characters, items and events: left out.
            # Chibi spin-offs (Pure Pure Pleiades, Isekai Quartet) and Blu-ray extras: left out too.
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|mass for the dead|"
                           r"pure pure pleiades|isekai quartet|blu-ray|volume \d|booklet",
                           exclude_categories=NOISE_CATEGORIES + ("Mass for the Dead Items", "Mass for the Dead Events",
                                                                  "Mass for the Dead Characters", "Manga")),
        ),
    ),
    "evangelion": SeriesSource(
        id="evangelion",
        title="Neon Genesis Evangelion",
        wiki_host="evangelion.fandom.com",
        categories=(
            # Episodes are in an "Episode:" namespace (category listings only cover articles): listed
            # by title. "Episode:25'" (the End of Evangelion versions) is left out.
            CategorySource("episode", "Episodes", titles=tuple(f"Episode:{n:02d}" for n in range(1, 27))),
            # Not excluding "Game characters": Shinji, Rei and Misato are in it too.
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("angel", "Angels", exclude_titles=NOT_ARTICLES),
            CategorySource("mecha", "Evangelions", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Terminology", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Technology", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|^episode:|^file:",
                           exclude_categories=NOISE_CATEGORIES + ("Pachinko", "Collaboration", "Crossover", "Publications",
                                                                  "Galleries", "Songs with Lyrics", "Neon Genesis Evangelion ANIMA")),
        ),
    ),
    "gintama": SeriesSource(
        id="gintama",
        title="Gintama",
        wiki_host="gintama.fandom.com",
        categories=(
            # "Episode 1-2" is one page for both parts (its infobox number is 1).
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!episode \d+(-\d+)?$)"),
            # Chapters are "Lesson N" (read as chapter N); "Lesson 360.5" is a bonus.
            CategorySource("chapter", "Chapters", exclude_titles=r"^(?!lesson \d+$)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|ginpachi|^lessons and volumes$|"
                           r"^episode |^lesson ", exclude_categories=NOISE_CATEGORIES),
        ),
    ),
    "steins_gate": SeriesSource(
        id="steins_gate",
        title="Steins;Gate",
        wiki_host="steins-gate.fandom.com",
        categories=(
            # "S;G (anime) - Ep.01" (number from the infobox's episodeNumber); specials left out.
            CategorySource("episode", "Episodes", exclude_titles=r"^(?!s;g \(anime\) - ep\.\d+$)"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|^s;g0? \(anime\) - ep|"
                           r"^s;g chapter", exclude_categories=NOISE_CATEGORIES),
        ),
    ),
    "steins_gate_0": SeriesSource(
        id="steins_gate_0",
        title="Steins;Gate 0",
        wiki_host="steins-gate.fandom.com",
        categories=(CategorySource("episode", "Episodes", exclude_titles=r"^(?!s;g0 \(anime\) - ep\.\d+$)"),),
        shares_with="steins_gate",
    ),
    "mushoku_tensei": SeriesSource(
        id="mushoku_tensei",
        title="Mushoku Tensei: Jobless Reincarnation",
        wiki_host="mushokutensei.fandom.com",
        categories=(
            # Episodes are numbered per season and manga chapters carry no number: unnumbered pages.
            CategorySource("anime_episode", "Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("manga_chapter", "Chapters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|volume \d",
                           exclude_categories=NOISE_CATEGORIES),
        ),
    ),
    # Manga-first series.
    "berserk": SeriesSource(
        id="berserk",
        title="Berserk",
        wiki_host="berserk.fandom.com",
        categories=(
            # The manga calls its chapters "episodes" ("Episode 120 (Manga)"), listed by arc.
            CategorySource("chapter", "Black Swordsman Arc Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Golden Age Arc Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Conviction Arc Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Millennium Falcon Arc Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("chapter", "Fantasia Arc Episodes", exclude_titles=NOT_ARTICLES),
            # Two anime adaptations with their own episode 1: unnumbered pages.
            CategorySource("anime_episode", "Episodes (1997 Anime)", exclude_titles=NOT_ARTICLES),
            CategorySource("anime_episode", "Episodes (2016 Anime)", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Black Swordsman Arc Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Golden Age Arc Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Conviction Arc Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Millennium Falcon Arc Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("character", "Fantasia Arc Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("race", "Apostles", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Magic", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Metaphysics", exclude_titles=NOT_ARTICLES),
            CategorySource("object", "Objects", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|^episode ",
                           exclude_categories=NOISE_CATEGORIES + ("Interviews",)),
        ),
    ),
    "vagabond": standard_series("vagabond", "Vagabond", "vagabond.fandom.com"),
    "kagurabachi": standard_series("kagurabachi", "Kagurabachi", "kagurabachi.fandom.com"),
    # Kingdom's chapter pages ("Chapter 120") are uncategorised: taken from all articles.
    "kingdom": standard_series("kingdom", "Kingdom", "kingdom.fandom.com",
                               CategorySource("chapter", ALL_ARTICLES, exclude_titles=r"^(?!chapter \d+$)"),
                               skip=r"^volumes and chapters|^omake$|^vol\.\d"),
    # Marvel: the wiki has ~49,000 articles (9,000 characters, mostly minor). Scoped to the
    # released movies and the pages they link to (~4,000: who and what the movies are about).
    "mcu": SeriesSource(
        id="mcu",
        title="Marvel Cinematic Universe (movies)",
        wiki_host="marvelcinematicuniverse.fandom.com",
        categories=(
            CategorySource("movie", "Released Movies"),
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("object", "Items", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("object", "Weapons", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("organization", "Organizations", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("organization", "Teams", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("event", "Events", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES, linked_from="Released Movies"),
        ),
    ),
    "yu_yu_hakusho": standard_series("yu_yu_hakusho", "Yu Yu Hakusho", "yuyuhakusho.fandom.com"),
    # Yashahime (the sequel) has its own "Episode 1 (Hanyō no Yashahime)": left out by the standard rule.
    "inuyasha": standard_series("inuyasha", "Inuyasha", "inuyasha.fandom.com",
                                CategorySource("character", "Individuals", exclude_titles=NOT_ARTICLES),  # its "Characters"
                                skip=r"yashahime"),
    "mashle": standard_series("mashle", "Mashle: Magic and Muscles", "mashle.fandom.com"),
    "undead_unluck": standard_series("undead_unluck", "Undead Unluck", "undead-unluck.fandom.com"),
    "noragami": standard_series("noragami", "Noragami", "noragami.fandom.com", skip=r"^aragoto episode"),
    "akame_ga_kill": standard_series("akame_ga_kill", "Akame ga Kill!", "akamegakill.fandom.com",
                                     skip=r"\(zero\)|\(hinowa ga yuku!\)"),
    "dorohedoro": standard_series("dorohedoro", "Dorohedoro", "dorohedoro.fandom.com"),
    # JoJo: chapter numbers restart with each Part (infobox "chapter = 1 (114)"), so each Part is a
    # series with its own chapters, sharing the base series' characters, Stands and episodes.
    "jojo": SeriesSource(
        id="jojo",
        title="JoJo's Bizarre Adventure",
        wiki_host="jojo.fandom.com",
        categories=(
            CategorySource("character", "Characters", exclude_titles=NOT_ARTICLES),
            CategorySource("stand", "Stands", exclude_titles=NOT_ARTICLES),
            CategorySource("concept", "Concepts", exclude_titles=NOT_ARTICLES),
            CategorySource("arc", "Story arcs", exclude_titles=NOT_ARTICLES),
            CategorySource("location", "Locations", exclude_titles=NOT_ARTICLES),
            # Episodes are titled by name and numbered per season: unnumbered pages.
            CategorySource("anime_episode", "Season 1 Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("anime_episode", "Season 2 Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("anime_episode", "Season 3 Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("anime_episode", "Season 4 Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("anime_episode", "Season 5 Episodes", exclude_titles=NOT_ARTICLES),
            CategorySource("page", ALL_ARTICLES, exclude_titles=NOT_ARTICLES + WIKI_NOISE + r"|\(chapter\)$|"
                           r"^(sbr|jjl|tjl) chapter|author's note|^volume \d",
                           exclude_categories=NOISE_CATEGORIES + ("Song", "Manga volumes", "Real People", "Animator")),
        ),
    ),
    "jojo_phantom_blood": SeriesSource(
        id="jojo_phantom_blood", title="JoJo Part 1: Phantom Blood", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Phantom Blood Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_battle_tendency": SeriesSource(
        id="jojo_battle_tendency", title="JoJo Part 2: Battle Tendency", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Battle Tendency Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_stardust_crusaders": SeriesSource(
        id="jojo_stardust_crusaders", title="JoJo Part 3: Stardust Crusaders", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Stardust Crusaders Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_diamond_is_unbreakable": SeriesSource(
        id="jojo_diamond_is_unbreakable", title="JoJo Part 4: Diamond Is Unbreakable", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Diamond Is Unbreakable Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_golden_wind": SeriesSource(
        id="jojo_golden_wind", title="JoJo Part 5: Golden Wind", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Vento Aureo Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_stone_ocean": SeriesSource(
        id="jojo_stone_ocean", title="JoJo Part 6: Stone Ocean", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Stone Ocean Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_steel_ball_run": SeriesSource(
        id="jojo_steel_ball_run", title="JoJo Part 7: Steel Ball Run", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "Steel Ball Run Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_jojolion": SeriesSource(
        id="jojo_jojolion", title="JoJo Part 8: JoJolion", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "JoJolion Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    "jojo_jojolands": SeriesSource(
        id="jojo_jojolands", title="JoJo Part 9: The JOJOLands", wiki_host="jojo.fandom.com",
        categories=(CategorySource("chapter", "The JOJOLands Chapters", exclude_titles=NOT_ARTICLES + r"|author's note"),),
        shares_with="jojo",
    ),
    # Boruto lives on naruto.fandom.com: the same infobox flags that keep it out of Naruto select it
    # here. Characters are shared with Naruto (Boruto, Kawaki and Sarada are already collected there).
    "boruto": SeriesSource(
        id="boruto",
        title="Boruto: Naruto Next Generations",
        wiki_host="naruto.fandom.com",
        categories=(
            CategorySource("episode", "Episodes", where=(("boruto anime", "yes"),)),
            CategorySource("chapter", "Chapters", where=(("boruto", "yes"), ("blue vortex", "no|"))),
        ),
        shares_with="naruto",
    ),
    # Two Blue Vortex restarts at chapter 1.
    "boruto_two_blue_vortex": SeriesSource(
        id="boruto_two_blue_vortex",
        title="Boruto: Two Blue Vortex",
        wiki_host="naruto.fandom.com",
        categories=(CategorySource("chapter", "Chapters", where=(("blue vortex", "yes"),)),),
        shares_with="naruto",
    ),
}
